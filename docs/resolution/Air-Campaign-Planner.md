# Doctrine-driven air campaign planner

The auto planner can plan each turn the way a Western Joint Force Air Component Commander
(JFACC) would. It works from the top down:

1. assess the campaign,
2. pick a campaign phase,
3. build a prioritized target list,
4. split the sorties between mission types,
5. build packages sized to the threat,
6. lay them out on a deconflicted timeline.

Each turn is one 6 hour air tasking order (ATO) period. You choose which part of it to fly in
DCS. The fast-forward combat model fights the rest.

Factions with Western doctrine use it by default. Other factions keep the legacy planner. Both
can be changed per side.

## Turning it on

Settings > Campaign Management > HQ Automation:

| Setting | What it does |
|---|---|
| Air campaign planner (OWNFOR / OPFOR) | **By faction doctrine** (Western doctrine uses the new planner), **Doctrine-driven air campaign (JFACC)**, or **Legacy priority planner**. |
| Air tasking order period (hours) | How much of the day one turn plans, 1–6 hours. The default is 6. |
| Acceptable attrition per sortie override | Replaces the doctrine's loss limits (see [Risk](#risk-and-scrubbing)). 0 keeps the doctrine's limits. |

Which doctrine uses the new planner is set by `planning_profile:` in
`resources/combat/doctrines.yaml`. The planning profile itself, with every number on this page, is
`resources/doctrine/planning/western.yaml`.

## Campaign phases

The planner moves through Desert Storm style phases. A phase lasts at least two turns. It moves on
when the measures of effectiveness (MOEs) for that phase are met.

| Phase | Focus | Moves on when |
|---|---|---|
| 0 Posture | Defensive counter-air, protecting high-value assets, building the picture | The war starts (turn 1) |
| I Strategic air campaign | IADS command nodes, airfields, the enemy air force | C2 ≥ 50% degraded, air superiority ≥ 1.5:1, enemy fighters ≥ 25% destroyed |
| II SEAD rollback | SAM sites over the battle area | Known battle-area SAMs ≤ 35% of the start, air superiority held |
| III Battlefield preparation | Fielded forces, LOCs, kill boxes | Enemy front-line strength ≥ 35% destroyed |
| IV Ground offensive | CAS and interdiction ahead of the main effort, air assault | (last phase) |
| DEFENSE (override) | CAS, DCA and interdiction against the enemy's attack | Enters on an enemy offensive warning, a threatened base, or a bad force ratio. Leaves when the front is stable, then resumes the phase it left. |

Each phase sets the share of sorties for each mission type, with a floor and a ceiling. Sorties a
mission type can't use go to the others, in the order set in the profile.

## What gets planned

* **Targets (JIPTL).** Only targets your intelligence has detected can be nominated. Each target
  is ranked by:
  * the phase's weight for its target system,
  * its value,
  * how close it is to the main effort,
  * the intel confidence,
  * how much of the desired effect is still missing.

  After a strike, battle damage assessment is uncertain. A target is struck again if it is
  assessed below the desired effect. Mobile targets drop off the list once their intel is two
  turns old.
* **Enablers.** AEW&C and tankers fly continuously across the period, with reliefs. Packages get
  tankers when their target is beyond unrefueled range. Carriers with enough fixed-wing sorties
  get a recovery tanker.
  * Doctrine decides this (`enablers.tanker_continuous` and `recovery_tanker`). The "Automatic
    Theater tanker package planning" setting only affects the legacy planner.
* **Defensive counter-air:**
  * CAP stations sit on each enemy threat axis, outside SAM coverage.
  * HVAA CAP covers the AEW&C and tanker tracks.
  * Point defense covers carriers.
  * QRA ground alert is held at threatened bases. Those fighters are reserved for the whole period
    and given no other mission. Neither the combat model nor the DCS mission scrambles them yet.
* **Ground support.** CAS vul windows cover fronts with troops in contact, weighted toward the
  main effort, and are spread over the period. Each CAS flight's expected kills are worked out
  from its actual loadout (an A-10C two-ship with Mavericks and CBUs is about 12 vehicles; an
  F/A-18C much less). Windows are tasked until the expected kills reach the desired effect for the
  period: 30% of the estimated enemy at the front, 40% in the ground offensive, 50% in defense.
  Kill boxes beyond the front get BAI or armed reconnaissance when they hold known targets.
* **Air assault (Phase IV).** Helicopter-borne troops seize enemy bases ahead of the main effort.
  An objective is chosen only when all of these hold:
  * the ground offensive phase is active,
  * air superiority is at least 1.5:1,
  * the base isn't blocked by enemy battle positions,
  * the base is within 60 nm of the main effort,
  * the landing zone is outside known radar SAM coverage, and its air threat is medium or lower.

  At most two air assaults are planned each period.
* **Packages** are sized to the threat along the planned route:
  * sweep and escort against fighters,
  * SEAD and jammers against radar SAMs,
  * enough strikers for the target's aim points.

  Weaponeering picks loadouts by guidance. At night only aircraft with sensors are used for attack
  missions. Laser and TV guided weapons aren't planned under a low cloud base. Missing support
  scrubs the package, except CAS for troops in contact and defensive packages, which fly with what
  is available if the risk allows.

## Buying aircraft

The planner files a request for forces every turn. The side's procurement then buys against it
within the budget, after planning. Purchases follow **Automate aircraft reinforcements** for your
side and are always on for the AI.

1. **A standing CSAR force first.** If CSAR is enabled for the side, the planner keeps 4
   CSAR-capable aircraft owned or on order across its CSAR squadrons
   (`procurement.csar_ready` in the doctrine file). Pilots are only rescued if helicopters are
   already on hand when they go down, so this can't wait for a shoot-down.
1. **Shortfalls next**, in the order they were found while planning:
   * a flight with no aircraft free in its sortie window,
   * SEAD a package needed to stay within its risk limit,
   * SEAD for a route into radar SAM coverage.
2. **Replacements** for squadrons below strength, up to 4 aircraft per squadron each turn. The
   squadrons flying the mission types the current phase apportions most come first.

Aircraft can only be bought for existing squadrons with room, pilots and parking.

## Sorties and timing

* Only the mission-capable share of each squadron flies (80%).
* An airframe can fly a second sortie in the period after its turnaround (2 hours for fighters,
  4 for bombers, 1.5 for helicopters). A second sortie doesn't take more aircraft from the
  squadron.
* Strike packages are placed in four waves through the period. SEAD and DEAD open each wave.
  Packages whose targets are within 15 nm of each other are kept at least 6 minutes apart.

## Risk and scrubbing

Every package gets an estimate of expected losses per sortie. The estimate comes from:

* the known SAM sites covering its planned route,
* an allowance for mobile SAMs intelligence hasn't found,
* the enemy fighters within reach,
* the SEAD, jammers, escorts and AEW&C supporting it.

The estimate is fitted to what the fast-forward combat model actually does to packages. Overlapping
SAM sites compound, and SEAD removes at most about half the threat.

| Package | Acceptable losses per sortie |
|---|---|
| Routine | 2% |
| High-value target | 3% |
| Defense | 4% |
| Troops in contact | 6% |
| Phase I / II | ×1.5 / ×1.25 |
| DEAD against the outermost SAM layer, Phase I/II (route SAM weight ≤ 8) | up to 10% |
| Any package | 8% at most, unless the rollback allowance above applies |

The rollback allowance exists because the fast-forward combat model is far deadlier against an
intact modern IADS than history. Without it the planner would never start the rollback.

The **Air campaign** page of the Intelligence window shows:

* the phase, the commander's intent and the MOEs,
* the apportioned and planned sorties,
* the JIPTL with BDA,
* the QRA ground alert,
* why packages were scrubbed.

Each package's dialog shows the reason it was planned and its estimated attrition.

## Reading the ATO

The package list on the left groups packages by mission category, in the order DCA, support,
OCA, SEAD/DEAD, strike, interdiction, CAS, personnel recovery and lift. Within each category they
are sorted by TOT. Each category has a coloured header with its package and sortie counts.

* **Category chips.** The chips above the list show each category with its package count. Click a
  chip to hide or show that category. Selecting a flight on the map shows its category again.
* **Package rows.**
  * The first line shows the package and target, then the TOT and how far it falls into the ATO
    period (for example `+1:25`).
  * The second line shows the composition, with main flights first.
  * Badges on the right show player slots, **DCS** if the package flies in the DCS window, pilots
    still needed, and the estimated losses per sortie. The loss estimate is green below 2%, amber
    below 5% and red above that.
* **Tooltips.** Hover a package to see why it was planned, the phase, the threat, the risk against
  its limit, and every flight's times.
* **Flight rows.** Each flight shows its role (for example CAS, SEAD, Escort or Jammer), its size
  and type, and its start, take-off, TOT or time on station, and landing.

**Timeline** under the package list, or **View → ATO timeline**, opens the whole period as a
Gantt chart.

* **Lanes.** Each package gets a lane, grouped and coloured like the list. Continuous lines share
  one lane, with relief packages alternating between two tracks, so a gap in coverage stands out.
  Continuous lines are CAP stations, AEW&C and tanker tracks, and CAS at one front.
* **Bars.**
  * A thin line runs from start-up to take-off, and the bar runs from take-off to landing.
  * A diamond marks the TOT, and a lighter band marks time on station.
  * Player packages are outlined in green.
  * Packages outside the DCS window are dimmed.
* **Interaction.**
  * Click a bar to select the package in the list and on the map.
  * Double-click a bar to edit the package.
  * Hold Ctrl and use the mouse wheel to zoom. **Fit** shows the whole period.

## Flying a window of the period

When the ATO covers more than one mission's worth of time, **Take off** first asks which window
to fly. The slider moves in 15 minute steps. A compact timeline shows the window against the
plan, and the friendly packages in the window are listed below it.

* Everything before the window is fought by the combat model first. Flights still airborne when
  the window starts spawn in flight at the right place.
* Packages that start after the window are left out of the mission. The combat model fights them
  once your DCS results are in, and their losses, strike results and intelligence are committed
  with the turn.
* Player flights are always flown in DCS.
* Ground combat at the front belongs to the window only.

## Checking it without DCS

`resources/tools/campaign_e2e.py` runs a campaign headless. For each side planned by the JFACC
planner, it prints per turn:

* the phase,
* planned against apportioned sorties,
* the sortie mix,
* package sizes,
* second sorties,
* estimated against actual loss rate.

`resources/tools/jfacc_report.py` prints one turn's plan, the JIPTL and the reasons packages were
scrubbed.

```
.venv/Scripts/python resources/tools/campaign_e2e.py --turns 4 --seed 3
.venv/Scripts/python resources/tools/jfacc_report.py --turns 1 --jiptl 20
```
