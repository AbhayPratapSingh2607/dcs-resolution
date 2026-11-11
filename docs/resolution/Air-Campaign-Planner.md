# Doctrine-driven air campaign planner

The auto planner can plan each turn the way the side's air force would: a Western Joint Force
Air Component Commander (JFACC), a Russian or Soviet air operation, a client state's air
defense, or an irregular force's handful of aircraft. It works from the top down:

1. assess the campaign,
2. pick a campaign phase,
3. build a prioritized target list,
4. split the sorties between mission types,
5. build packages sized to the threat,
6. lay them out on a deconflicted timeline.

Each turn is one 6 hour air tasking order (ATO) period for both sides: routine lines all
period, strike waves, and a main push. You fly one flight of it; the DCS mission is the slice of
the war around that flight (the bubble), and the fast-forward combat model fights everything
else over the whole period. Turns advance 6 hours, so day and night cycle. The older **Mission
only** model, which plans just one mission, is kept as an option (see
[Mission only](#mission-only)) and gets no new features.

Every doctrine except WWII uses it by default, each with its own planning profile (see
[Doctrines](#doctrines)). WWII factions keep the legacy planner. Both can be changed per side.

The planner plans from its own side's intelligence picture, never from ground truth: enemy
aircraft numbers are estimates, SAM sites it believes destroyed are planned around as destroyed,
and enemy flights it never saw teach it nothing.

## Turning it on

Settings > Campaign Management > HQ Automation:

| Setting | What it does |
|---|---|
| Air campaign planner (OWNFOR / OPFOR) | **By faction doctrine** (Western doctrine uses the new planner), **Doctrine-driven air campaign (JFACC)**, or **Legacy priority planner**. |
| Mission only | Off by default: the full 6 hour turn. On: each turn plans one mission window plus a lead-in (see [Mission only](#mission-only)). A change applies from the next turn. |
| Mission only: lead-in (minutes) | How long before the mission starts flights may take off, 0–90. The default is 30. |
| Mission only: packages per side (guidance) | Roughly how many combat packages each side plans, 4–40. The default is 10. |
| Air tasking order period (hours) | With mission only off: how much of the day one turn plans, 1–6 hours. The default is 6. |
| Full turn: only what you'd meet is in DCS (the bubble) | On by default. Off: every package flying during the DCS window is in the mission (see [The bubble](#the-bubble)). |
| Full turn: packages per side in DCS (guidance) | With the bubble on: about how many packages of each side, besides yours and its support, go into DCS, 2–60. The default is 10. |
| Strategic surprise at H-hour (Campaign Doctrine > Warfare) | How ready the enemy is when the war starts; also set in the opening dialog (see [The opening](#the-opening)). |
| Acceptable attrition per sortie override | Replaces the doctrine's loss limits (see [Risk](#risk-and-scrubbing)). 0 keeps the doctrine's limits. |

Which planning profile a doctrine uses is set by `planning_profile:` in
`resources/combat/doctrines.yaml`. The profiles, with every number on this page, are in
`resources/doctrine/planning/`. A profile can `extends:` another and change only what differs.

## A turn, start to finish

1. **Begin Campaign** (turn 0 only) opens the opening choices: H-hour, the opening emphasis,
   the strategic surprise and the pre-war reconnaissance. The opening missile strikes fly and
   turn 1 starts at H-hour. See [The opening](#the-opening).
2. **Both commanders plan the 6 hour period** from their own intelligence: the phase, the target
   list, the sortie split, packages sized to the threat, and a timeline of routine lines, strike
   waves and one main push. See [What gets planned](#what-gets-planned) and
   [Sorties and timing](#sorties-and-timing).
3. **You get a flight.** The **Your flight** card offers flights from the real plan, ranked by
   your squadron and mission type preference; the plan never bends to it. Or plan your own
   packages by hand. See [Your seat](#your-seat).
4. **Read the plan.** The briefing opens on the period: the phase and intent, the main push,
   your package, and what the enemy is expected to do. The ATO list folds routine lines and
   waves; the timeline shows the main push in amber and the DCS window in blue. See
   [Reading the ATO](#reading-the-ato).
5. **Take off.** The DCS mission starts when your flight starts up. Everything earlier in the
   period is fought by the combat model first. Without a player flight you pick a window or
   fast-forward the turn. See [The DCS window](#the-dcs-window).
6. **The bubble.** Only the packages you are likely to meet go into DCS, about 10 per side;
   the rest are fought by the combat model over the same time. See [The bubble](#the-bubble).
7. **After the mission.** When you quit, the flights that hadn't finished, the packages
   elsewhere and the packages after the mission are fought by the combat model, and their
   results are committed with the turn. See [After the mission](#after-the-mission).
8. **The debrief** shows the period in parts: your mission, elsewhere during it, before it and
   after it, with the commander's assessment for the next turn.

## The opening

**Begin Campaign** opens the opening choices:

* **H-hour**: which 6 hour period of the day the war starts in.
* **Opening emphasis**: air defenses, airfields, command and control, or balanced. It weights the
  turn 1 target list and the opening missile strikes.
* **Strategic surprise** (also in the settings): how ready the enemy is. With none, many of its
  mobile SAMs have left their known sites, its mobile radars wait in ambush on turn 1, its decoys
  are out, its aircraft are dispersed and an extra alert pair sits at each fighter base. With full
  surprise its SAMs are where intelligence saw them, radiating, without decoys, its aircraft parked
  in the open, and one alert pair fewer.
* **Pre-war reconnaissance**: a number of enemy bases (more with better ISR) to look at; each
  raises what intelligence knows within 40 nm. The enemy reconnoitres its own.

Begin Campaign then starts the war at H-hour, puts the enemy in its posture, flies the
reconnaissance, runs the first strategic intel round, and fires blue's opening missile salvo:
cruise missiles from the faction's era (none before 1983 for Western factions, Russia from 2015),
raised by the cruise missile ships and bomber detachments in the campaign, at fixed targets from
the target list weighted by the emphasis. Hit chances depend on the target, the SAMs around it and
the surprise. There is no missile stock afterwards. The turn 1 briefing opens with the opening
estimate and the BDA: what was fired at and what intelligence assesses was hit, with its
uncertainty. The damage shows on the map, and in the first mission as wrecks and craters.

Squadrons and detachments start with their aircraft; nothing is bought at turn 0. Strategic
bombers sit at off-map bases only, and the commander offers them first for strikes and runway
attacks; they still need SEAD into radar SAM cover like everyone else.

## Your seat

Set a preference at the air wing step of a new campaign, or with **Preference…** on the
**Your flight** card above the package list: a squadron, a mission type, or both. It never
changes the plan. After the commander has planned the turn, its flights are ranked for you:
your squadron's flights first, then your mission type, then anything else you can fly; in each,
the main push first, then key packages, then by time on target. With the planning behaviour
**No preference** the top offer is yours: one of its pilots becomes the player, and the rest of
the plan flies with AI pilots. The card lists the next offers; **Take** moves you, and so does
**Take this flight** in a package's context menu, or putting yourself in any flight by hand.
When the plan has nothing for your preference the card says why, from the plan's own records.

**Planning by hand.** The behaviour **Commander flies routine lines, you plan the rest** keeps
the CAPs, AWACS, tankers and ground alerts planned for you and leaves the strikes to you. Your
packages are key packages in the briefing and the debrief. **Keep in my mission** on a package
pins it for the DCS mission.

## The DCS window

With a player flight, the DCS window starts when your flight starts up, and the mission is as
long as the desired mission duration. Without one, **Take off** asks whether to fast-forward the
turn, fly an AI-only window or go back. For an AI-only window the window picker asks which part
of the period to fly: the slider moves in 15 minute steps, a compact timeline shows the window
against the plan, and the friendly packages in the window are listed below it.

* Everything before the window is fought by the combat model first. Flights that took off
  earlier are on their routes when the mission starts, spawned in flight at the right place,
  and flights past their time on target are heading home without the weapons they dropped.
* Packages that start after the window are left out of the mission. The combat model fights them
  once your DCS results are in (see [After the mission](#after-the-mission)).
* Player flights are always flown in DCS.
* Ground combat at the front belongs to the window only.

## The bubble

In a full turn with a player flight, the DCS mission holds only what you are likely to meet.
Always in: your package, the nearest tanker and AWACS on station, SEAD and DEAD striking on
your route just before or during the mission, and packages you pinned with **Keep in my
mission**. The rest is scored from the flight plans minute by minute: an enemy CAP whose commit
region covers your route, an alert pair whose sector does, a package crossing your route within
15 nm at about the same time, near your target or base. A CAP and the raid it would commit on go
in together. About **Full turn: packages per side in DCS** packages of each side (10 by default)
fill the rest, most likely first; it is guidance, not a limit.

The combat model fights the packages elsewhere over the mission's own time, apart from DCS, and
carries on when you quit. Their aircraft still on the ramp at your base are parked there.
Your flight card shows what the mission will hold, **Bubble…** lists every package with its
reason, the package tooltip gives it too, packages elsewhere fold by group in the list and are
dimmed on the map, and the debriefing reports them as **Elsewhere during the mission**. Turn it
off with **Full turn: only what you'd meet is in DCS**.

`resources/tools/bubble_distortion.py SAVE --seeds 5` measures what keeping the two apart costs:
it fights the save's window whole and split and compares losses.

## After the mission

When you quit DCS, the flights in the mission that hadn't finished are carried on by the combat
model from where their plans put them at that time. The packages elsewhere (the bubble) and the
packages planned for after the mission are fought too, until the period ends and the last
flights land. Their air losses, strike results, runway damage and intelligence are committed
with the turn; the ground war at the front and base captures by ground forces belong to the
mission.

Some missions take effect through a script in the DCS mission: rescues (CSAR), FARP deliveries
(CTLD) and base captures (capture zones). For AI flights the mission never had, because they
flew before the window, elsewhere or after it, the combat model's result counts instead: a
surviving CSAR flight rescues its pilot, a surviving FARP setup flight delivers the FARP, and a
surviving air assault takes its objective if the base has no armor left to hold it. Flights in
the mission, and every flight with a player, count only what the mission reports.

## Reading the ATO

A 6 hour plan has dozens of packages, so the list folds it (the **Fold** chip, on by default):

* each routine line (a CAP station, an AWACS or tanker track, a base's ground alert) is one row
  with its reliefs inside: "BARCAP — CAP 040", with the number of packages, sorties and the span
  of their times on target;
* the main push is open: every package in it has its own row;
* the other waves are one row per category: "Strike before the main push", "SEAD / DEAD after
  the main push".

Click a folded row's badge (▸ 4) to open it and the ▾ badge on its first row to close it again.
Hovering a folded row lists what is inside. Selecting a package from the timeline or the map
opens its fold. The **Fold** chip shows every package.

On the map, routine lines are drawn as a small dashed circle at their station with the line's
name on hover, instead of their full racetrack. Click one, or select the package in the list, to
see its route. Packages with players and strike packages keep their routes. The timeline shades
the main push in amber and the DCS window in blue.

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

# How the commander plans

## Campaign phases

Phases are data in the planning profile: each has its mission shares, target weights and flags
(ground stance, raids, risk), and transitions to other phases when measures of effectiveness
(MOEs) are met. Interrupts (such as a defense against an enemy offensive) take over from any
offensive phase and resume it when they're over. Modifiers, such as force preservation, overlay
the current phase without replacing it.

The Western profile moves through Desert Storm style phases. A phase lasts at least two turns.

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
  * CAP stations sit on each enemy threat axis, outside SAM coverage. Axes run toward enemy
    fighter bases, and toward where the side has actually seen enemy aircraft come from (see
    [Adaptation](#adaptation)).
  * HVAA CAP covers the AEW&C and tanker tracks.
  * Point defense covers carriers.
  * Ground alert pairs wait at threatened bases and are scrambled by GCI (see
    [Ground alert and GCI](#ground-alert-and-gci)).
* **Ground support.** CAS vul windows cover fronts with troops in contact, weighted toward the
  main effort, and are spread over the period. Each CAS flight's expected kills are worked out
  from its actual loadout (an A-10C two-ship with Mavericks and CBUs is about 12 vehicles; an
  F/A-18C much less). Windows are tasked until the expected kills reach the desired effect for the
  period: 30% of the estimated enemy at the front, 40% in the ground offensive, 50% in defense.
  Kill boxes beyond the front get BAI or armed reconnaissance when they hold known targets.
* **FAC(A).** With a western doctrine, each CAS package over the main effort takes an optional
  second CAS element as its airborne forward air controller, when a type that can fly the DCS
  AFAC task is free. It flies with the CAS under the same escort, finds and marks targets and
  talks the CAS on instead of attacking. In DCS it gets the AFAC task and a FAC task on its
  flight frequency, and it is listed on the kneeboard with the JTACs. In the combat model,
  CAS on that front while the FAC(A) is overhead hits more often with visual, rocket and laser
  weapons (laser weapons count as designated). The package's rationale names the FAC(A).
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

## Doctrines

| Profile | Used by | How it fights |
|---|---|---|
| `western` | NATO and Western-trained air forces | Desert Storm phases: strategic attack, SEAD rollback, battlefield preparation, ground offensive. Packages with SEAD, jammers and escort; low risk limits. |
| `russian_modern` | Modern Russia and peers | Readiness, then an initial air operation of massed raids for three turns, then the front offensive. Defends with PVO and front defense phases. Strikes without SEAD if it must; higher risk limits. |
| `soviet` | Soviet and Cold War Warsaw Pact | Like `russian_modern`, with bigger, more widely spaced raids, low-level ingress, unguided weapons first and more mobile SAM ambushes. |
| `client` | Client states (Iraq, Iran, Syria, North Korea...) | Homeland air defense first; limited offensives when the balance allows. Hides its air force and IADS when losing. |
| `irregular` | Insurgents and militias | Survives; harasses with small packages; no enablers, no ground alert. |

* **Massed raids** (`russian_modern`, `soviet`). The most important targets (airfields, command
  nodes, long-range SAMs, early warning radars) get a raid instead of a package: a suppression
  echelon against the SAM sites on the route, the main strike group with a fighter clearing
  element, and a follow-up group, each a package of its own minutes apart. The raid is planned
  whole or not at all. Packages of a raid share a raid id, shown in their planning details.
* **Low-level ingress** (doctrines with `strike_altitude: low`). Strikers fly ingress and egress
  at 500 ft AGL in DCS, and the risk estimate trades radar SAM exposure for guns and short-range
  SAMs along the track.
* **Force preservation.** When a side's air losses mount or it is losing the air battle, it
  pulls its CAPs back under its own SAMs, stops raids, cuts offensive sorties, puts more fighters
  on ground alert and hides its most-hunted SAM sites.

## Adaptation

Each side keeps a picture of where the enemy's air operations come from: the bearings, per own
base, at which its own early warning radars and AWACS saw enemy aircraft during the turn, and
where its own aircraft and ground units were hit. Older observations fade each turn. The learned
axes move CAP stations and ground alert stations, guide SAM moves and decide where decoys go.

## IADS management

Sides whose profile manages its IADS (`iads.manage`, every profile except `western`):

* **Emission control.** Each radar SAM site gets an order every period:
  * *active*: radiates and fights as part of the network.
  * *ambush*: radars dark until the target is close, then a short engagement. Hard for ELINT and
    anti-radiation hunters to find. The default for mobile sites in `soviet` and `client`.
  * *dark*: silent to survive, firing only in self-defense. Given to the most hunted sites under
    force preservation, never to more than a set share of the IADS.

  The orders apply in the fast-forward combat model and are passed to Skynet in DCS.
* **Moving SAM sites.** At the start of each turn, some mobile SAM sites relocate: a site that
  fired last turn shoots and scoots a few km, a site the enemy keeps hitting drives away, and a
  site that would cover an observed threat axis better moves there. New positions are on own
  ground, behind the front, on dry, level, open ground and apart from other sites. The enemy
  isn't told: its intel picture and any decoys stay at the old position until it finds the site
  again.
* **Decoys.** Doctrines with deception keep decoys beside each radar SAM site, placed toward the
  observed threat axis where the enemy looks first.

## Ground alert and GCI

Fighter pairs on ground alert (QRA) wait at the runway end of threatened bases, each with a CAP
station on the base's main threat axis and a sector around it. Their aircraft are held for the
whole period.

The side's ground-controlled interception (GCI) watches its own radar picture (early warning
radars and AWACS, with radar horizon and jamming). When it sees an enemy raid inside an alert's
sector, it scrambles the nearest pairs: one pair per two raiders, up to the doctrine's limit per
raid (`alert.max_scrambles_per_raid`). The pair takes off and flies to its station, engaging
what it finds there. A dead or jammed radar network scrambles nothing, and alerts never
scrambled don't fly.

* **Fast-forward:** the combat model runs the GCI every tick.
* **DCS:** alert groups are late activated with no trigger. The **GCI ground alert scrambles**
  plugin (on by default) activates them by the same rules from what the coalition's EWRs and
  AWACS detect. Without the plugin, alert fighters never launch in DCS.

## Fog of war and the enemy's plan

With fog of war on (soft or strict), the enemy's ATO, its view in the ATO timeline and its air
campaign tab are hidden. You know the enemy's air operations only from the flights your radars
see on the map. With fog of war off, all of it is shown, and the enemy's ATO can be edited as
before.

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
* Strike packages are placed in waves through the period. SEAD and DEAD open each wave.
  Packages whose targets are within 15 nm of each other are kept at least 6 minutes apart.
* **The main push.** In a full turn each commander puts the turn's main effort into one block as
  long as the desired mission duration. SEAD and DEAD open it at H-hour (5 minutes in), the
  strikes follow 8 minutes later through the corridors they open, then a follow-up wave. About
  half of each offensive category's sorties go into the push (`main_push_share`); the rest fly in
  the smaller waves before and after it, and at least one wave always comes before it. Where the
  push sits is the commander's choice from its own doctrine (`main_push_start_min`): about
  2 hours in for a Western air force, 100 minutes for a modern Russian one and 90 for a Soviet
  one, whose massed raids are its push. A client air force masses only 30% of its packages; an
  irregular one spreads everything over the period. Each side picks its own time from its own
  picture, so the two pushes may or may not overlap. The DCS window picker opens on blue's push.
  Air assaults go in the push, ahead of the main effort.

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

Against a dense IADS even the outermost sites can have a route SAM weight above 8. Then the two
least-defended SAM sites are **openers**: DEAD against them may accept up to 20%, so the rollback
starts somewhere.

**Loss experience.** The estimate is fitted to a few reference scenarios and can be well off
against other opponents. Each side compares the model's expected losses for its estimated
packages with the aircraft it actually lost on them, separately for strike packages and CAP
stations. Later estimates are multiplied by (lost + 3) / (expected + 3), between ×0.35 and ×3.
The history fades by 30% a turn. A scrub reason shows the factor ("x0.45 from losses so far").
Only the side's own losses count, which it always knows. The constants are in the profile under
`risk.experience`.

**SEAD corridors.** A package with HARM shooters suppresses the airspace along their route from
10 minutes before its time on target to 20 after. A package whose ingress lies in such a corridor
at its time on target doesn't need its own HARM escort, and the corridor's shooters count in its
estimate. SEAD and DEAD are planned first, in the first wave, so the strikes of the next wave can
use their corridors.

CAPs are estimated too, with the defense limit. A CAP orbits near the edge of SAM coverage and
turns away rather than pressing through it to a target. Overlapping sites don't compound against
it, so its SAM exposure grows linearly with the route's SAM weight rather than with its square.
SAM sites within 15 nm of its station count at reduced weight, since the CAP turns and chases
near there and the site's position may be off. If a station is still over the limit, it's
pulled back along its threat axis (half the distance, then over the defended base) before
the CAP line is dropped.

**Mission only and enemy fighters.** The share of enemy fighters able to engage
(`enemy_fighter_availability`) describes a 6 hour ATO. In a mission only turn both air forces fly the
turn's sorties within the mission window, so the share is scaled by 6 hours over the window,
up to 1.

The **Air campaign** page of the Intelligence window shows:

* the phase, the commander's intent and the MOEs,
* the apportioned and planned sorties,
* the JIPTL with BDA,
* the QRA ground alert,
* why packages were scrubbed.

Each package's dialog shows the reason it was planned and its estimated attrition.

## Mission only

The mission only model (the "focused turn" of the changelog) plans only what the mission needs.
It is kept as an option and gets no new features:

* **The period is the lead-in plus the mission.** With a 60 minute mission and a 30 minute
  lead-in, the turn plans 90 minutes. The mission starts when the lead-in ends.
* **Flights already in the air.** A package that took off during the lead-in is flown there by
  the combat model, and it appears in the mission where it is by then. Flights that take off
  later start at their base.
* **Every time on target is inside the mission:** from H-hour, 5 minutes after the mission
  starts, to 15 minutes before its planned end, so packages can strike and egress in the mission.
* **One CAP per station.** A CAP stays on station until the mission's planned end (90 minutes at
  most), so it isn't relieved. AEW&C and tankers stretch their time on station by up to half
  again for the same reason. A line isn't relieved for its last 15 minutes. Stations within
  10 nm of each other are merged.
* **About 10 combat packages per side.** Once a side has as many CAP, strike, SEAD,
  interdiction and CAS packages as the guidance, it stops adding strike, SEAD, interdiction and
  CAS packages. Personnel recovery, AEW&C, tankers, HVAA CAPs and ground alerts don't count,
  and raids may go over.
* **Returning flights.** Each side also has two CAPs that flew the shift before. They leave
  their station just before the mission starts and are on their way home when it opens. They
  are real sorties: their aircraft are busy, they can be intercepted, and losses count. They
  don't count toward the package guidance.
* **Fuel.** AI flights already in the air when the mission starts have used fuel getting
  there, but never so much that they can't finish their plan with a reserve. External tanks
  are full.
* **There's no window to pick.** **Take off** goes straight to the mission.
* **Nothing happens between missions.** The rest of the 6 hour step is quiet. Repairs,
  purchases, intelligence decay and SAM moves still happen between turns.

Peer test (USA 2005 against Russia 2010, Caucasus, 60 minute mission): blue planned 12 packages
instead of 25, red 15 instead of 29. Against Iraq 1991, blue planned 12 instead of 35.

## Checking it without DCS

`resources/tools/campaign_e2e.py` runs a campaign headless. For each side planned by the JFACC
planner, it prints per turn:

* the phase,
* planned against apportioned sorties,
* the sortie mix,
* package sizes,
* second sorties,
* estimated against actual loss rate.

It also prints active modifiers, raids, ground alerts held and scrambled, IADS orders and
moves, and the learned threat axes. It then lists:

* losses by task, with the estimate for each;
* why packages were scrubbed;
* the scrubbed packages that came closest to their risk limit.

The tool runs under a fixed `PYTHONHASHSEED` (`--hash-seed`, default 0). Python randomizes string
hashing per process, which changes set order and with it the plan, so without this two runs with
the same `--seed` can differ (for example, Iran turn 1 in "strategic" or in "defense").

`resources/tools/jfacc_report.py` prints one turn's plan, the JIPTL and the reasons packages were
scrubbed.

`resources/tools/campaign_matrix.py` plays scenarios over several seeds in parallel and checks
them against bands:

| Scenario | Band |
|---|---|
| `iraq`, `iran` | Blue loses at most one aircraft per five red, and red takes no base. |
| `peer` (Russia 2010 against the US) | Exchange ratio between 0.5 and 2.5; neither side takes more than one base. |
| `red_wins` (Russia against Georgia 2008) | Red takes a base within 6 turns in 3 of 5 seeds. |

```
.venv/Scripts/python resources/tools/campaign_e2e.py --turns 4 --seed 3
.venv/Scripts/python resources/tools/jfacc_report.py --turns 1 --jiptl 20
.venv/Scripts/python resources/tools/campaign_matrix.py --scenarios iraq peer --seeds 5 --workers 2
```
