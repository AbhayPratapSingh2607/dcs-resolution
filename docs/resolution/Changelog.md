# Resolution changelog

Changes in Resolution on top of DCS Retribution. Retribution's own changes are listed in the main
[changelog](../../changelog.md).

## Features

* **[CSAR]** Turn-based combat search and rescue. Downed pilots appear on the map and survive for a
  set number of turns. AI and player helicopters can rescue them, with hover or landing extraction
  for the AI and MOOSE Ops.CSAR for players. Unrescued pilots go missing in action or are taken
  prisoner, and prisoners are freed when their base is retaken. Rescued pilots recover for a few
  turns. Pilots who come down near a base are resolved automatically. Nearby pilots can be collected
  by one flight. Rescues and captures are listed in the debriefing, and the settings cover each part
  of the system. (Retribution PR #929) [Guide](CSAR.md)
* **[FARPs]** Dynamic FARPs. Place Wet Wing (C-130) or Fat Cow (CH-47) FARPs on friendly ground near
  the front from the top bar, with live site checks on the map. A transport delivers the equipment
  in the mission. Helicopter detachments fly in from their parent squadrons and can be recalled.
  FARPs cost upkeep. They are lost if they are overrun or their fuel is destroyed, and you get a
  warning when the front gets close. Terrain grids are included for 13 theaters, and there is an
  instant-FARP cheat. [Guide](Dynamic-FARPs.md)
* **[Loadouts]** Payloads are listed by their mission editor label. Payload editor stations use
  mission editor station labels, and each station's weapons are sorted into category submenus.
  [Guide](Loadout-Editor.md)
* **[Modding]** Support for the UH-60L Armed Blackhawk submod (v7.1.4) and the ANDR0ID Weapon Pack.
  Airframe selection, ESSS stub wings, 32 extra stores, and the submod's loadout rules are applied
  in the editor and at mission generation. [Guide](Armed-Blackhawk.md)
* **[Flight Planning]** New start type: **On Station**. The flight appears in the air at its
  station: the start of the racetrack for CAP, AWACS and tankers, the IP for attack packages. It
  appears at its planned time there, or at mission start with ASAP. Support assets no longer need
  a fast-forward to be on station. [Guide](On-Station-Start.md)
* **[Auto Planner]** Doctrine-driven air campaign planner (Western JFACC). Each turn is planned as
  one 6 hour air tasking order:
  * Desert Storm style campaign phases with a DEFENSE override.
  * A prioritized target list from detected targets only, with desired effects and uncertain BDA.
  * Sortie apportionment by phase, with mission-capable rates, turnaround and second sorties.
  * Packages sized to the threat on the planned route, weaponeering with night and weather
    gates, and an estimated-attrition limit fitted to the combat model.
  * Continuous AEW&C, tanker, CAP and HVAA CAP lines, QRA ground alert, CAS vul windows sized to
    the desired effect from each flight's loadout, kill boxes, and Phase IV air assault.

  Before take off you pick which window of the period to fly in DCS. The combat model fights
  what comes before and after it. Western factions use the planner by default, and the legacy
  planner can be chosen per side. The planner buys aircraft through a request for forces: the
  shortfalls that limited the plan first, then replacements for squadrons below strength. The
  Intelligence window has a new Air campaign page.
  [Guide](Air-Campaign-Planner.md)
* **[Auto Planner]** The air campaign planner now plans for every doctrine except WWII, each the
  way its air force fights:
  * Planning profiles for Russian, Soviet, client-state and irregular doctrines, with their own
    phases, risk limits and package rules. Phases are now data in the profile, and profiles can
    extend each other.
  * Soviet and Russian massed raids: suppression, main strike group with fighter clearing, and
    follow-up echelons minutes apart. Low-level ingress for Soviet-style doctrines, in DCS and in
    the risk estimate.
  * Force preservation when losing: CAPs under own SAMs, raids stopped, more fighters on alert,
    hunted SAM sites go dark.
  * Each side learns the enemy's attack axes from what its own radars saw and where it was hit,
    and moves CAP stations, alert stations, SAM sites and decoys to match.
  * IADS management: emission control orders (active, ambush, dark) for each SAM site, in the
    combat model and Skynet; mobile SAM sites relocate between turns, leaving the enemy's intel
    stale; decoys placed toward the threat.
  * Ground alert fighters are scrambled by GCI from the side's own radar picture, in fast-forward
    and in DCS (new **GCI ground alert scrambles** plugin).
  * Planning uses only the side's intel picture: estimated enemy aircraft and SAM sites believed
    alive, not ground truth.
  * With fog of war on, the enemy's ATO, timeline and air campaign plan are hidden.
  * `campaign_matrix.py` checks the planners over several seeds against historical bands.

  [Guide](Air-Campaign-Planner.md#doctrines)
* **[Campaign AI]** The planner keeps 4 CSAR helicopters owned or on order and buys them before
  any other aircraft, so pilots who go down can be rescued.
* **[Campaign AI]** The planner keeps a theater tanker track and carrier recovery tankers going
  according to its doctrine. The "Automatic Theater tanker package planning" setting now only
  affects the legacy planner.
* **[Fast Forward]** Bases can be captured in a turn fought entirely by fast forward. Before, only
  the DCS mission's capture triggers could take a base, so a front fast-forwarded all the way to a
  base stopped there. A base now falls when its front strength is spent and it has no armor left,
  and the side attacking across that front still has at least 4 ground units on an aggressive,
  elimination or breakthrough stance. DCS missions still capture bases only through their triggers.
* **[UI]** The package list is easier to read:
  * Packages are grouped by mission category, with coloured headers and counts, and sorted by TOT.
  * Category chips hide or show each group.
  * Rows give the purpose, the composition, the TOT and its offset into the period, and badges for
    players, the DCS window, missing pilots and estimated risk.
  * Flight rows show each flight's role and key times.

  A new **ATO timeline** window (Timeline button, or View menu) shows the whole period as a Gantt
  chart, with relief chains in one lane and the DCS window shaded. The DCS window picker shows the
  same timeline. [Guide](Air-Campaign-Planner.md#reading-the-ato)

* **[Auto Planner]** **The main push.** With **Mission only** off, each commander puts the
  turn's main effort into one block as long as the desired mission duration: SEAD and DEAD at
  H-hour, strikes minutes later through their corridors, then a follow-up. About half of the
  offensive sorties go into it; the other waves are smaller and come before and after it. Where
  it sits is set per doctrine, and each side picks its own. The DCS window picker opens on
  blue's push. Red's massed raids are its push.
* **[UI]** The ATO list folds a 6 hour plan to one screen: each routine line is one row with
  its reliefs inside, the main push is open, and the other waves are one row per category. A
  click on the row's badge opens it; the **Fold** chip shows everything. On the map, routine
  lines are a station symbol until selected, and the timeline shades the main push.
* **[Auto Planner]** The focused turn is now the **Mission only** option (same setting, renamed).
  It is kept as it is and gets no new features; the 6 hour turn is where new work goes.
  `campaign_e2e.py` and `campaign_matrix.py` take `--turn-model {full,mission-only}`.
* **[Auto Planner]** **Focused turns**, on by default. Each turn plans the air war of one mission,
  the desired mission duration plus a 30 minute lead-in, instead of a 6 hour ATO:
  * flights that took off during the lead-in are already in the air when the mission starts;
  * every time on target falls inside the mission, with time to egress;
  * one CAP per station covers the whole mission, with no reliefs for its last minutes;
  * about 10 combat packages per side (a setting, as guidance);
  * two CAPs per side that flew the previous shift are on their way home when the mission
    starts;
  * AI flights already airborne spawn with the fuel they'd have left (enough to finish their
    plan), not a full load.

  Turns still advance 6 hours, so day and night cycle, and there's no window to pick. In a peer
  test blue planned 12 packages instead of 25. The 6 hour period is still available with the
  setting off. [Guide](Air-Campaign-Planner.md#focused-turns)

* **[Plugins]** New **Parking cleanup** plugin, on by default. It removes AI aircraft 10 minutes
  after they land and shut down, so ramps and carrier decks stay free and frame rate holds up.
  Player aircraft are never removed, helicopters only if the option is set, and the removal
  isn't counted as a loss.

* **[Auto Planner]** SEAD covers a corridor, not one package. A strike flying through airspace
  that an earlier SEAD or DEAD package is suppressing at its time on target no longer needs its own
  HARM escort, and SEAD and DEAD are planned first, so the strikes after them can use those
  corridors. SEAD-capable squadrons are no longer used up escorting one package each.

* **[Auto Planner]** Against a dense IADS, where even the outermost SAM sites are too risky for
  the normal limits, the two least-defended sites may be attacked at up to 20% expected losses
  each turn, so the rollback can start.

* **[Auto Planner]** The planner checks its risk estimates against its own losses. If its
  packages lose fewer aircraft than estimated, later estimates come down, and the reverse,
  within limits (x0.35 to x3) and fading over a few turns. Against Iran blue went from flying
  only CAPs after turn 1 to flying SEAD, DEAD and CAS every turn.

* **[Auto Planner]** A turn briefing at the top of the ATO panel and in the DCS mission briefing:
  the phase and intent, the key packages and what each is for, the routine lines in one line, and
  the threats as the side's own intelligence sees them.

* **[Auto Planner]** Risk estimates in focused turns:
  * enemy fighter availability is scaled to the mission window, since both air forces fly the
    turn's sorties in it;
  * a CAP station's SAM exposure grows linearly with the SAM weight on its route;
  * a CAP station over the risk limit is pulled back along its axis instead of dropped.

  Before, against Iran's IADS blue could end up flying no CAP at all once red's SAMs moved up.

* **[Debriefing]** The debriefing opens with **How the plan went**. Each key package shows its
  goal, what it achieved (target destroyed, hits, air kills, aborted, not flown) and what it
  lost. CAP stations and support get one summed line each. The full loss lists follow.

## Fixes

* **[Auto Planner]** CAP packages get a risk estimate. Before they had none, so a turn of CAPs
  reported 0% while losing 2–4% per sortie to SAMs. The estimate counts SAM sites near the station
  and is fitted to what the combat model does to CAPs. CAPs no longer get SEAD escorts added.

* **[Fog of War]** Changing the fog of war or intelligence setting now refreshes the map. Before,
  the map kept what it showed under the old setting until the next turn: with fog of war turned
  off, enemy routes stayed hidden and sites stayed marked unconfirmed. Turning fog of war on also
  hides the enemy's ATO again if it was shown.
* **[Skynet]** The autonomous behaviour of SAM sites (go dark when cut off from the network) now
  reaches Skynet as the number it expects; before, every site behaved as DCS AI.
* **[Fast Forward]** Air engagements in which nobody fired no longer restart every second. A CAP
  that couldn't catch an enemy inside its commit range (an AWACS turning away) started a new,
  empty engagement each tick; the pair now waits 5 minutes before engaging again. In one turn this
  cut air engagements from 166 to 29.
* **[UI]** Before **Begin Campaign**, the ATO panel says the pre-war posture plan is never flown;
  the first real plan is made when the campaign begins.
* **[Fast Forward]** A second sortie whose airframes were shot down earlier in the period is
  cancelled. Before, the lost airframes flew it, and their losses could exceed the squadron's
  aircraft.

* **[New Game]** Creating a campaign from a script no longer fails because the "squadrons start
  full" option wasn't passed to the generator.

* **[Modding]** Creating Super Hornet flights with CJS Super Hornet v2.4.6 no longer fails with
  "could not convert string to float". Local constants used as pylon keys in Lua payload files are
  now resolved. [Details](Super-Hornet.md)
* **[Modding]** Super Hornet pylon weapons use the current pydcs weapon identifiers.
* **[Modding]** Fixed the Super Hornets' malformed callsign table.
* **[Flight Planning]** Passing the turn no longer fails with "Could not plan AEW&C ... is outside
  the navmesh" when a base is deep inside the enemy's threat zone. The AEW&C orbit is pulled back
  until it can be reached, and a package that still can't be planned is scrubbed. This is also
  offered upstream on branch `aewc-navmesh-fix`.
