# Resolution changelog

What Resolution adds to DCS Retribution, grouped by area. Each entry describes the feature as it
is now. Retribution's own changes are in its [changelog](../../changelog.md).

## The six hour war

* **[Turn]** Each turn is six hours of air war for both sides. The commanders plan all of it:
  routine lines with reliefs, strike waves, and one main push as long as the desired mission
  duration. You fly one flight. The combat model fights everything before your mission,
  everything outside the bubble during it, and everything after you quit. Turns still advance
  six hours, so day and night cycle. [Guide](Playing-a-Turn.md)
* **[Turn]** The mission starts where fast forward stops for your earliest player flight (its
  startup, taxi, takeoff or IP, following **Fast forward until**). When the commander frags you,
  or you put yourself in another flight, the window moves to it. Without a player flight,
  **Take off** asks whether to fast-forward the turn, fly an AI-only window, or go back.
  [Guide](Playing-a-Turn.md#the-dcs-window)
* **[Turn]** Drag the DCS window on the ATO timeline or in the window picker; it snaps to 15
  minutes. A window you placed stays at Take off while every player flight starts inside it.
* **[Bubble]** Only what you are likely to meet goes into DCS: your package and its support, the
  SEAD on your route, pinned packages, enemy CAPs and alerts covering your route, and packages
  crossing it. That is about 10 packages per side. A CAP and the raid it would fight go in
  together. The combat model fights the rest over the same time. **Bubble…** and the tooltips
  say why each package is in or out, the map dims the rest, and the debriefing has an
  **Elsewhere during the mission** part. [Guide](Playing-a-Turn.md#the-bubble)
* **[Turn]** After you quit, the flights that hadn't finished are carried on by the combat model
  from where their plans put them, then the packages planned later. FARP setup flights, air
  assaults and CSAR flights flown by the combat model take effect.
* **[Turn]** AI flights past their time on target appear heading home without the air-to-ground
  weapons they dropped, with their missiles, pods and tanks.
* **[Turn]** **Mission only** keeps the older model, which plans one mission plus a lead-in.
  It is off by default and gets no new features. A campaign keeps the model it was saved with.
  [Guide](Playing-a-Turn.md#mission-only)

## The opening

* **[Opening]** **Begin Campaign** asks for H-hour, the opening emphasis, the strategic surprise
  and the pre-war reconnaissance areas. It then flies both sides' reconnaissance, runs the first
  intel round, and puts the enemy in its posture: moved SAMs, emission control, decoys,
  dispersal and alert fighters. Then it fires blue's opening cruise missile salvo. The turn 1
  briefing opens with the estimate and the BDA. [Guide](Playing-a-Turn.md#the-opening)
* **[Opening]** The opening window lists the planned salvo target by target and follows the
  emphasis as you change it. **Fire the opening salvo**, and the **Opening missile strikes**
  setting, turn it off. The map marks the salvo's targets on turn 0.
* **[Opening]** The enemy's reaction follows the strategic surprise. With no surprise, its
  engineers reopen the cut runways next turn, half its fighters and attack aircraft fly from road
  bases meanwhile, and its missile units fire back on turn 1. With full surprise, the runways stay
  shut for four turns, only 10% fly from roads, and nothing fires back.
* **[Road bases]** A red squadron on a cratered airfield keeps flying part of its aircraft from
  road strips; they start in the air 6–15 km from the field. The share follows the surprise and
  grows each turn. Helicopters all fly, and bombers, tankers, AWACS and transports stay grounded.
  Blue has no road bases. Setting: **Road base operations**.
  [Guide](Playing-a-Turn.md#road-bases)
* **[Campaign start]** Squadrons and detachments start with their aircraft, for both sides.
  Nothing is bought at turn 0, which spends the budget on ground forces.

## The commanders

* **[Commanders]** Doctrine-driven air campaign planning for every doctrine except WWII:
  * campaign phases (Desert Storm-style for the West) with defense interrupts and modifiers;
  * a target list from detected targets only, with desired effects and uncertain BDA;
  * apportionment with mission-capable rates, turnaround and second sorties;
  * packages sized to the threat on the route, with weaponeering and night and weather gates;
  * a risk limit fitted to the combat model, which learns from the side's own losses;
  * continuous AEW&C, tanker, CAP and HVAA CAP lines, QRA ground alert, CAS sized to the desired
    effect, kill boxes, FAC(A) and Phase IV air assault.

  The legacy planner can be chosen per side. [Guide](Air-Campaign-Planner.md)
* **[Commanders]** Planning profiles for Russian, Soviet, client-state and irregular doctrines,
  each with its own phases, risk limits and package rules:
  * Soviet and Russian massed raids: suppression, a main strike group with fighter clearing, and
    follow-up echelons, with low-level ingress for Soviet-style doctrines.
  * Force preservation when losing.
  * Each side learns the enemy's attack axes and moves CAP stations, alerts, SAMs and decoys to
    match.

  [Guide](Air-Campaign-Planner.md#doctrines)
* **[Commanders]** IADS management: emission control orders (active, ambush, dark) for each SAM
  site, in the combat model and in Skynet. Mobile SAM sites relocate between turns, leaving the
  enemy's intel stale, and decoys are placed toward the threat.
  [Guide](Air-Campaign-Planner.md#iads-management)
* **[Commanders]** Ground alert fighters are scrambled by GCI from the side's own radar picture,
  in fast forward and in DCS (the **GCI ground alert scrambles** plugin).
* **[Commanders]** SEAD covers a corridor, not one package. Strikes through suppressed airspace
  don't need their own HARM escort, and SEAD and DEAD fly first. Air defense ships are threats
  on a route and are attacked in the suppression wave.
* **[Commanders]** Tanker tracks follow the receivers: a boom line for land-based boom receivers,
  a drogue line off each carrier or LHA with probe squadrons, and a drogue line for land-based
  probe aircraft, up to 3. A package's tanker matches its strikers' system.
  [Guide](Air-Campaign-Planner.md#what-gets-planned)
* **[Commanders]** A standing CSAR force of 4 helicopters is bought before any other aircraft. A
  request for forces buys for shortfalls first, then replacements.
* **[Commanders]** A jet flying its second sortie of the turn keeps the crew of its first.
* **[Your seat]** Name a squadron or mission type. Each turn the commander frags you the best
  match from its plan, and the **Your flight** card lists the next offers; **Take** moves you. The
  plan never changes for your preference. [Guide](Playing-a-Turn.md#your-seat)
* **[Your seat]** **Commander flies routine lines, you plan the rest** leaves the strikes to you.
  **Keep in my mission** pins a package for DCS.

## The combat model

* **[Combat model]** Fast forward can fight it out: air-to-air in phases (detection, BVR,
  defense, the merge, decisions), SAMs as launchers, magazines and radars with a combat Pk chain,
  attack runs with real loadouts against point defenses, and Lanchester front lines with
  breakpoints. Weather degrades specific capabilities. It is calibrated against Desert Storm,
  Allied Force, Linebacker II and Yom Kippur. Setting: **Resolve combat when fast forwarding
  by**. [Guide](Combat-Model.md)
* **[Combat model]** Force quality by faction: training, readiness, IADS integration and
  doctrine differ, as they did historically.
* **[Combat model]** Fuel margins and tankers: short-legged strikes are rushed or abort, fighters
  reach bingo sooner, and a tanker shot down stops supporting its flights.
* **[Combat model]** Every loss records where and how the aircraft went down. Pilots come down
  there, and the chance of ejecting depends on the kind of hit.
* **[Combat model]** Bases can be captured in a fast-forwarded turn when the defending front is
  spent and has no armor left.
* **[Debriefing]** An after-action report for each side: losses by cause and type, crew fates,
  front-line losses, achievements and intelligence sources, with key events.
* **[Debriefing]** **How the plan went** opens the debriefing, split into the parts of the turn.
  Each key package shows its goal and what it achieved, and a CSAR package reads "pilot rescued"
  or "pilot not picked up".

## Intelligence

* **[Intel]** Each side keeps its own picture of the enemy, from pre-war intelligence, ELINT,
  sightings, engagements, strike reports and reconnaissance (new **Recon** mission type). The
  commanders plan only against what they know, unknown SAM sites achieve surprise, and BDA can
  be wrong. [Guide](Intelligence.md)
* **[Fog of war]** The map shows blue's picture: Strict hides undetected sites and shows detected
  ones at their estimated position, Soft marks unconfirmed ones. Each site says how it was
  detected, when and how confidently. With fog of war on, the enemy's ATO is hidden.
* **[Intel]** Imaging satellites (optical and radar, limited by weather and light) and
  intelligence agencies (order of battle, site tips, warnings, battle damage), for both sides by
  the same rules.
* **[Intel]** Deception: decoys beside mobile air defenses fool imagery and agents. A package sent
  at a decoy gets one roll to see through it, and DCS and the combat model follow the same call.
* **[Intel]** Morale for squadrons, ground forces and SAM crews; national war-weariness; rules of
  engagement and collateral damage near built-up areas.
* **[Intel]** The Intelligence window has an **Intel picture** page and an **Air campaign** page.

## Fire missions

* **[Fire missions]** Both sides plan Tomahawk, Scud, V-1 and artillery strikes every turn. Strikes
  inside the DCS mission are fired in DCS by the launcher. The rest are fired by the combat model.
  [Guide](Fire-Missions.md)
* **[Fire missions]** Right-click an enemy site or airfield, then **Plan Fire Mission…**, to plan
  a strike with its odds. The Fire Missions window adds, suggests and removes strikes.
* **[Fire missions]** Campaign magazines for ships and missile sites, with no reloads (setting
  **Limited missile stocks**). Missiles can target located mobile sites at half the hit chance.
* **[Fire missions]** Your commander plans fire missions with the ATO, using half of each
  launcher's capacity. Setting: **Commander plans your fire missions**.
* **[Timeline]** Fire missions have their own section on the ATO timeline, one lane per launcher,
  drawn from launch to impact and draggable. Strikes that would overlap stack in rows.
* **[Map]** Planned strikes are marked on the map with the strikes in the target's tooltip.

## Aircrew, helicopters and bases

* **[CSAR]** Turn-based combat search and rescue. Downed pilots appear on the map and survive for a
  set number of turns. AI and player helicopters can rescue them, with hover or landing extraction
  for the AI and MOOSE Ops.CSAR for players. Unrescued pilots go missing in action or are taken
  prisoner, and prisoners are freed when their base is retaken. Rescued pilots recover for a few
  turns. (Retribution PR #929) [Guide](CSAR.md)
* **[CSAR]** Rescues by AI helicopters in the combat model count in the mission results window
  before you accept, not only after.
* **[Rescue King]** Place a C-130 orbit from the FARPs menu, outside enemy air defenses, for one
  turn. Up to 2 CSAR helicopters stage under it and start in the air over it. Pick the King
  aircraft and its time on station. Rescue flights are kept inside it, and it can be dragged on
  the timeline. [Guide](CSAR.md#rescue-king)
* **[FARPs]** Dynamic FARPs. Place Wet Wing (C-130) or Fat Cow (CH-47) FARPs on friendly ground near
  the front from the top bar, with live site checks on the map. A transport delivers the equipment
  in the mission. Helicopter detachments fly in from their parent squadrons and can be recalled.
  FARPs cost upkeep, and they are lost if they are overrun or their fuel is destroyed. Terrain
  grids are included for 13 theaters. A maximum distance of 0 removes the limit.
  [Guide](Dynamic-FARPs.md)
* **[Flight Planning]** New start type: **On Station**. The flight appears in the air at its
  station: the start of the racetrack for CAP, AWACS and tankers, the IP for attack packages.
  [Guide](On-Station-Start.md)
* **[Plugins]** **Parking cleanup** removes AI aircraft 10 minutes after they land and shut down,
  so ramps and decks stay free and frame rate holds up.

## Air wings and aircraft

* **[Air wing]** The **Air Wing Setup** window for new campaigns, built around presets by base.
  Carriers, LHAs and airfields are ranked from closest to farthest from the battle. Every
  faction has its own presets made from its aircraft (134 factions, up to 17 each), and the
  historical presets follow: US Navy carrier air wings 1975–2020, USMC ARGs, USAF expeditionary
  forces, NATO, Soviet and Russian air forces. Presets fit the base's parking, and include
  helicopters and off-map bomber detachments. The old editor is still there as **Advanced
  editor…**. [Guide](Air-Wing-Presets.md)
* **[Loadouts]** Payloads are listed by their mission editor label. Stations use mission editor
  labels, and each station's weapons are sorted into category submenus.
  [Guide](Loadout-Editor.md)
* **[Modding]** Support for the UH-60L Armed Blackhawk submod (v7.1.4) and the ANDR0ID Weapon Pack.
  [Guide](Armed-Blackhawk.md)
* **[Modding]** CJS Super Hornet v2.4.6 payloads load: local constants used as pylon keys are
  resolved. Pylon weapons use current pydcs identifiers, and the callsign table is fixed.
  [Guide](Super-Hornet.md)

## The interface

* **[ATO]** The package list is grouped by mission category with coloured headers, counts and
  category chips. Rows give the purpose, composition, TOT and its offset, and badges for players,
  the DCS window, missing pilots and estimated risk.
* **[ATO]** A six hour plan folds to one screen: each routine line is one row with its reliefs
  inside, the main push is open, and the other waves fold by category. A fold's open/close
  toggle is a tab on the card's right edge, and an opened fold's packages come straight under its
  first row.
* **[ATO]** The **Your flight** tab has your flight card and the full turn briefing.
* **[Timeline]** The **ATO timeline** shows the whole period as a Gantt chart. It has relief
  chains in one lane, the main push and DCS window shaded, and draggable packages, fire missions
  and window. [Guide](Playing-a-Turn.md#the-ato-timeline)
* **[Map]** Routine lines are a station symbol until selected.
* **[UI]** **Take off**, fast forward and processing the results show a progress window with the
  step and elapsed time. Closing it during Take off or fast forward cancels.
* **[UI]** The settings window has a search box, and each setting's description sits below it.
  The debriefing opens in two columns, and the results window grows to fit the combat log.

## Fixes

* **[Air wing]** Presets only offer the faction's aircraft as its mod settings leave them.
  Carrier presets include a tanker and SH-60B Seahawks. The S-3B's refueling priority of 0 had
  been read as "can't refuel".
* **[Parking]** Jets can no longer overfill an airfield that also has helicopters. Free parking
  for jets is limited by the base's total, and a save already over capacity is trimmed when it
  loads.
* **[Fast forward]** "Fast-forward the turn" from the No player flight dialog fights the whole
  turn, whatever **Fast forward until** is set to. Before, the simulation stopped on its first
  tick.
* **[Fast forward]** A second sortie whose airframes were shot down earlier in the period is
  cancelled.
* **[Fast forward]** Air engagements in which nobody fired no longer restart every second.
* **[Combat model]** A HARM that hits a warship wrecks its radars instead of sinking it, and HARMs
  no longer hunt boats armed only with guns and MANPADS.
* **[Commanders]** DEAD flights carry weapons that hit a site with its radar off. A flight armed
  only with anti-radiation missiles flies SEAD escort instead.
* **[Commanders]** Only one AEW&C line per station.
* **[Commanders]** CAS risk estimates count the ground fire of the troops at the front, and CAS
  goes to the least exposed squadrons first.
* **[Mission generation]** An AI package that takes the decoy attacks the decoy group with its
  usual attack tasks.
* **[Mission generation]** Anti-ship flights fire at every ship of a group, each from a bearing
  with no other ship in the way.
* **[Mission generation]** With culling on, the mission only keeps ground units near what is in
  it, including parked aircraft and missile sites.
* **[Mission generation]** DCS no longer rejects a CAP whose racetrack start is already behind it
  at mission start.
* **[Briefing]** The DCS briefing is plain text, with friendly packages listed by time over
  target.
* **[Debriefing]** The plan report shows the turn just flown, and lists every package after a turn
  fought by the combat model.
* **[CSAR]** Simulated AI rescues are credited, and flights that leave the map end at their exit
  point instead of crashing the simulation.
* **[Fog of war]** Changing the fog of war or intelligence setting refreshes the map at once.
* **[Skynet]** The autonomous behaviour of cut-off SAM sites reaches Skynet.
* **[New game]** Creating a campaign from a script passes the "squadrons start full" option.
* **[Flight planning]** Passing the turn no longer fails with "Could not plan AEW&C ... is outside
  the navmesh". This is also offered upstream on branch `aewc-navmesh-fix`.
