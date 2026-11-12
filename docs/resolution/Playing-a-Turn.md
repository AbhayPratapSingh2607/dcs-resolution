# Playing a turn

This is the biggest difference from Retribution. In Retribution a turn is one mission, and the
ATO is built to fill it. In Resolution a turn is **six hours of air war for both sides**:

```
|----------------------------- 6 hour turn -----------------------------|

 routine lines: CAP, AWACS, tankers, ground alert, with reliefs =========
 wave       wave        [  MAIN PUSH  ]        wave       wave

 before the mission   |  during the mission       |  after you quit
 combat model         |  DCS: the bubble          |  combat model
                      |  combat model: the rest   |
```

Each side's commander plans all six hours (see [The commanders](Air-Campaign-Planner.md)). You
fly one flight of it. The DCS mission is the slice of the war around that flight. The
[combat model](Combat-Model.md) fights everything else: before your mission, elsewhere during
it, and after you quit. Turns advance six hours, so day and night cycle.

Any turn can be skipped. The combat model then fights all of it.

## A turn, start to finish

1. **Begin Campaign** (turn 0 only) opens the opening choices: H-hour, the opening emphasis,
   the strategic surprise and the pre-war reconnaissance. The opening missile strikes fly, and
   turn 1 starts at H-hour. See [The opening](#the-opening).
2. **Both commanders plan the six hours** from their own intelligence: routine lines all
   period, strike waves, and one main push.
3. **You get a flight.** The **Your flight** card offers flights from the real plan, ranked by
   your squadron and mission type preference. Or you plan your own packages by hand. See
   [Your seat](#your-seat).
4. **Read the plan.** The **Your flight** tab has the full turn briefing. The ATO list folds
   routine lines and waves, and the timeline shows the main push in amber and the DCS window
   in blue. See [Reading the ATO](#reading-the-ato).
5. **Take off.** The mission starts where fast forward stops for your flight. Everything
   earlier in the period is fought by the combat model first. See
   [The DCS window](#the-dcs-window).
6. **Fly.** Only the packages you are likely to meet are in DCS, about 10 per side. The rest
   are fought by the combat model over the same time. See [The bubble](#the-bubble).
7. **Quit.** The flights that hadn't finished, the packages elsewhere and the packages after
   your mission are fought by the combat model. See [After the mission](#after-the-mission).
8. **The debrief** shows the turn in parts: your mission, elsewhere during it, before it and
   after it. Then the commanders plan the next turn.

## The opening

In Retribution the war starts when you press Take off. In Resolution it starts with
**Begin Campaign**, which opens the opening choices:

* **H-hour**: which six hour period of the day the war starts in.
* **Opening emphasis**: air defenses, airfields, command and control, or balanced. It weights the
  turn 1 target list and the opening missile strikes.
* **Strategic surprise** (also a setting): how ready the enemy is.
  * With none, many of its mobile SAMs have left their known sites, its mobile radars wait in
    ambush on turn 1, its decoys are out, its aircraft are dispersed and an extra alert pair
    sits at each fighter base.
  * With full surprise its SAMs are where intelligence saw them and radiating, it has no
    decoys out, its aircraft are parked in the open, and it has one alert pair fewer.
* **Pre-war reconnaissance**: a number of enemy bases to look at (more with better ISR). Each
  one raises what intelligence knows within 40 nm. The enemy reconnoitres its own.
* **Opening missile strikes** (also a setting): the planned salvo, listed target by target with
  its type, the base it is near and the missiles aimed at it. The list follows the emphasis as
  you change it. Uncheck **Fire the opening salvo** to open the war without it. On turn 0 the
  map marks the same targets with a red ring.

Begin Campaign then starts the war at H-hour and puts the enemy in its posture. It flies the
reconnaissance, runs the first strategic intel round, and fires blue's opening salvo:

* **Missiles:** cruise missiles from the faction's era (none before 1983 for Western factions,
  Russia from 2015).
* **Launchers:** the cruise missile ships and bomber detachments in the campaign. The salvo
  draws on the ships' magazines.
* **Targets:** fixed targets from the target list, weighted by the emphasis.

Hit chances depend on the target, the SAMs around it and the surprise.

The turn 1 briefing opens with the estimate and the BDA: what was fired at, and what
intelligence assesses was hit, with its uncertainty. The damage shows on the map, and in the
first mission as wrecks and craters.

**How the enemy reacts follows the strategic surprise.** The BDA ends with what intelligence
expects:

| | No surprise | Partial | Full surprise |
|---|---|---|---|
| Runways cut by the salvo reopen after | 1 turn | 2 turns | 4 turns |
| Share flying from road bases on turn 1 | 50% | 25% | 10% |
| Counter-strike on turn 1 by its missile units | all of them | half | none |

Repairs on runways cut by the salvo start at once and cost the enemy nothing, because its
engineers were either ready for it or not. Runways cut later in the war follow the normal rules
(four turns once the repair is bought).

Squadrons and detachments start with their aircraft. Nothing is bought at turn 0, so turn 0
spends the budget on ground forces. Strategic bombers sit at off-map bases only.

### Road bases

An enemy squadron whose airfield runway is cratered keeps flying part of its aircraft from road
strips nearby, as air forces that expect war plan to. Its commander plans those sorties like any
other. The flights start in the air 6 to 15 km from their airfield ("took off from a road base"),
in DCS and in the combat model.

* Red's share follows the surprise at the opening (above). It grows by 10% a turn after turn 1,
  to 40% or the turn 1 share, whichever is higher.
* Only red flies from road bases. A cratered blue runway grounds everything there.
* Helicopters don't need a runway, so they all fly.
* Bombers, tankers, AWACS and transports stay grounded.

The flights land back at their airfield, because DCS doesn't show the craters. **Road base
operations** (Campaign Doctrine > Intelligence, morale and electronic warfare) turns this off.
A cratered runway then grounds everything there again.

## Your seat

In Retribution you pick any flight and the mission is built around it. In Resolution the
commander plans the war first and then offers you a seat in it. **The plan never changes for
you.**

**Set a preference** at the air wing step of a new campaign, or with **Preference…** on the
**Your flight** card (the **Your flight** tab of the left panel). It can be a squadron, a mission
type or both.

After the commander has planned the turn, its flights are ranked for you:

1. your squadron's flights, then your mission type, then anything else you can fly;
2. within each of those, the main push first, then key packages, then by time on target.

**With the planning behaviour "No preference",** the top offer is yours. One of its pilots
becomes the player, and the rest of the plan flies with AI pilots.

**Changing flight:** the card lists the next offers, and **Take** moves you. So does **Take this
flight** in a package's context menu, or putting yourself in any flight by hand. When the plan
has nothing for your preference, the card says why, from the plan's own records.

**Planning by hand.** The behaviour **Commander flies routine lines, you plan the rest** keeps
the CAPs, AWACS, tankers and ground alerts planned for you and leaves the strikes to you. Your
packages are key packages in the briefing and the debrief. **Keep in my mission** on a package
pins it for the DCS mission.

## The DCS window

**With a player flight,** the mission starts where fast forward stops for your earliest player
flight, and it is as long as the desired mission duration. Where it stops follows **Fast forward
until**:

* player startup, taxi or takeoff;
* player at IP;
* with any other setting, its startup.

When the commander frags you, or you put yourself in another flight, the window moves to it.

**Without a player flight,** **Take off** asks whether to fast-forward the turn, fly an AI-only
window, or go back. For an AI-only window, the window picker asks which part of the period to
fly. The slider moves in 15 minute steps. A compact timeline shows the window against the plan,
and the friendly packages in the window are listed below it.

**You can move the window yourself.** Drag the shaded band on the ATO timeline or in the picker;
it snaps to 15 minutes. A window you placed stays there at Take off as long as every player
flight starts inside it. You can't drag it in a Mission only turn, while viewing OPFOR's ATO, or
once part of the turn has been fought.

**How the window fits into the turn:**

* Everything before the window is fought by the combat model first. Flights that took off
  earlier are on their routes when the mission starts, spawned in flight at the right place.
  Flights past their time on target are heading home without the weapons they dropped.
* Packages that start after the window are left out of the mission. The combat model fights
  them once your DCS results are in.
* Player flights are always flown in DCS.
* Ground combat at the front belongs to the window only.

## The bubble

In a full turn with a player flight, the DCS mission holds only what you are likely to meet.

**Always in:**

* your package;
* the nearest tanker and AWACS on station;
* SEAD and DEAD striking on your route just before or during the mission;
* packages you pinned with **Keep in my mission**.

**The rest** is scored from the flight plans, minute by minute:

* an enemy CAP whose commit region covers your route;
* an alert pair whose sector does;
* a package crossing your route within 15 nm at about the same time, or near your target or
  base.

A CAP and the raid it would commit on go in together. About **Full turn: packages per side in
DCS** packages of each side fill the rest, most likely first. The default is 10, and it is
guidance, not a limit.

**The packages left out** are fought by the combat model over the mission's own time, apart
from DCS, and it carries on when you quit. Their aircraft still on the ramp at your base are
parked there.

**Where you see it:**

* your flight card shows what the mission will hold;
* **Bubble…** lists every package with its reason, and the package tooltip gives it too;
* packages elsewhere fold by group in the list and are dimmed on the map;
* the debriefing reports them as **Elsewhere during the mission**.

Turn it off with **Full turn: only what you'd meet is in DCS**.

## After the mission

When you quit DCS, the flights in the mission that hadn't finished are carried on by the combat
model from where their plans put them at that time. Then the packages elsewhere (outside the
bubble) and the packages planned for after the mission are fought, until the period ends and the
last flights land. Their air losses, strike results, runway damage and intelligence are
committed with the turn. The ground war at the front and base captures by ground forces belong to
the mission.

Some missions take effect through a script in the DCS mission: rescues (CSAR), FARP deliveries
(CTLD) and base captures (capture zones). For AI flights the mission never had, the combat
model's result counts instead:

* a surviving CSAR flight rescues its pilot;
* a surviving FARP setup flight delivers the FARP;
* a surviving air assault takes its objective, if the base has no armor left to hold it.

Flights in the mission, and every flight with a player, count only what the mission reports.

**The results window** lists both sides' losses and the combat log of the fast forward. Rescues
the combat model credited are counted there before you accept.

**The debriefing** opens with **How the plan went**, split into the parts of the turn: the
mission (DCS), elsewhere during it, before it and after it (combat model). Each key package
shows its goal and what it achieved, such as "target destroyed", "3 units hit", "pilot rescued"
or "aborted", and what it lost. CAP stations and support get one summed line each. The
[after-action report](Combat-Model.md#the-after-action-report) and the full loss lists follow.

## Reading the ATO

A six hour plan has dozens of packages. Retribution's flat list doesn't scale to that, so
Resolution folds it (the **Fold** chip, on by default):

* each routine line (a CAP station, an AWACS or tanker track, a base's ground alert) is one row
  with its reliefs inside: "BARCAP — CAP 040", with the number of packages, sorties and the span
  of their times on target;
* the main push is open: every package in it has its own row;
* the other waves are one row per category: "Strike before the main push", "SEAD / DEAD after
  the main push".

Click the tab on a folded row's right edge to open it, and again to close it. An opened fold's
packages come straight under its first row. Hovering a folded row lists what is inside.
Selecting a package from the timeline or the map opens its fold.

**The package list** groups packages by mission category, in this order: DCA, support, OCA,
SEAD/DEAD, strike, interdiction, CAS, personnel recovery and lift. Each category has a coloured
header with its package and sortie counts.

* **Category chips** above the list show or hide each category.
* **Package rows:**
  * The first line has the package, the target, the TOT and how far it falls into the period
    (`+1:25`).
  * The second line has the composition, with the main flights first.
  * Badges show player slots, **DCS** if the package flies in the DCS window, pilots still
    needed, and the estimated losses per sortie. The estimate is green below 2%, amber below
    5% and red above that.
* **Tooltips** say why the package was planned, the phase, the threat, the risk against its
  limit, and every flight's times.

**On the map,** routine lines are a small dashed circle at their station until selected, instead
of their full racetrack. Packages with players and strike packages keep their routes.

### The ATO timeline

**Timeline** under the package list, or **View > ATO timeline**, shows the whole period as a
Gantt chart.

* **Lanes.** Each package gets a lane, grouped and coloured like the list. Continuous lines (CAP
  stations, AEW&C and tanker tracks, CAS at one front) share one lane, with reliefs alternating
  between two tracks, so a gap in coverage stands out.
* **Bars.** A thin line runs from start-up to take-off, and the bar from take-off to landing. A
  diamond marks the TOT and a lighter band the time on station. Player packages are outlined in
  green, and packages outside the DCS window are dimmed.
* **Shading.** The main push is shaded amber and the DCS window blue.
* **Fire missions** have their own section, one lane per launcher, with each strike drawn from
  launch to impact. Strikes that would overlap stack in rows.
* **Interaction:**
  * Click a bar to select the package in the list and on the map. Double-click it to edit.
  * Drag a package to move its TOT.
  * Drag a fire mission to move it.
  * Drag the DCS window to move it.
  * Ctrl and the mouse wheel zoom, and **Fit** shows the whole period.
  * **Show OPFOR's ATO** shows the enemy's plan when fog of war allows it.

## Mission only

**Mission only** (off by default) is the older model, kept for those who want Retribution's
pacing. It plans only what one mission needs, and it gets no new features.

* **The period is the lead-in plus the mission.** With a 60 minute mission and a 30 minute
  lead-in, the turn plans 90 minutes.
* **Flights already in the air.** A package that took off during the lead-in is flown there by
  the combat model, and it appears in the mission where it is by then.
* **Every time on target is inside the mission**, from 5 minutes after it starts to 15 minutes
  before its planned end.
* **One CAP per station** covers the whole mission, with no reliefs.
* **About 10 combat packages per side**, as guidance.
* **Returning flights.** Each side has two CAPs from the shift before, already on their way home
  when the mission opens.
* **There's no window to pick.** **Take off** goes straight to the mission.
* **Nothing happens between missions.** The rest of the six hour step is quiet. Repairs,
  purchases, intelligence decay and SAM moves still happen between turns.

A campaign saved in either model loads and keeps its model. Changing the setting applies from
the next turn.

## Settings

Settings > Campaign Management > HQ Automation, unless noted:

| Setting | What it does |
|---|---|
| Mission only | Off: the six hour turn. On: each turn plans one mission plus a lead-in. |
| Mission only: lead-in (minutes) | How long before the mission flights may take off, 0–90. Default 30. |
| Mission only: packages per side (guidance) | 4–40. Default 10. |
| Air tasking order period (hours) | How much of the day one turn plans, 1–6. Default 6. |
| Full turn: only what you'd meet is in DCS | The bubble. On by default. |
| Full turn: packages per side in DCS (guidance) | 2–60. Default 10. |
| Fast forward until (Mission Generator > Gameplay) | Where your mission starts: your startup, taxi, takeoff or IP. |
| Strategic surprise at H-hour (Campaign Doctrine > Intelligence, morale and electronic warfare) | How ready the enemy is when the war starts. |
| Opening missile strikes (same section) | Blue's turn 0 salvo on or off. |
| Road base operations (same section) | Red keeps flying from road strips when its runways are cut. |
