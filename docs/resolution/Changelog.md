# Resolution changelog

Changes in Resolution on top of DCS Retribution. Retribution's own changes are listed in the main
[changelog](../../changelog.md).

## Features

* **[Fire missions]** Plan cruise missile, Scud and artillery strikes in regular turns.
  **Fire Missions** in the top bar (or **Plan fire mission…** on an enemy site) picks a
  launcher (Ticonderoga and Arleigh Burke ships, Scud sites, front-line artillery), a target in
  its reach, the rounds and the time; **Suggest** lets the commander fill the rest. Strikes timed
  inside the DCS mission are fired in DCS by the launcher itself; the rest are fired by the
  combat model at their time. Each launcher fires up to its capacity every turn, with no stock.
  Red's commander plans its own, and its turn 1 counter-strike follows the strategic surprise.
  Setting: **Fire missions**. [Guide](Fire-Missions.md)
* **[Opening]** The enemy's reaction to the opening salvo follows the strategic surprise. With
  no surprise its engineers reopen the cut runways next turn, half its fighters and attack
  aircraft fly from road bases meanwhile, and its missile units fire back on turn 1. With full
  surprise the runways stay shut for four turns, only 10% fly from roads and nothing fires back.
  The turn 1 BDA says what to expect. [Guide](Air-Campaign-Planner.md#the-opening)
* **[Air war]** Road bases. A cratered runway no longer grounds a whole air force: part of each
  squadron there (40% for blue; red's share follows the surprise and grows) flies from road
  strips and starts in the air a few miles from its airfield. Helicopters all fly on; bombers,
  tankers, AWACS and transports stay grounded. Setting: **Road base operations**.
  [Guide](Air-Campaign-Planner.md#road-bases)
* **[Opening]** The Begin Campaign window lists the planned opening missile strikes: each
  target, its type, the base it is near and the missiles aimed at it, following the opening
  emphasis as you change it. **Fire the opening salvo** turns the strikes off, and so does the
  new **Opening missile strikes** setting.
  [Guide](Air-Campaign-Planner.md#the-opening)
* **[FARPs]** Setting **FARP maximum distance from front** to 0 removes the limit: FARPs
  can be built any distance behind the front.
* **[Timeline]** Drag the DCS mission window on the timeline. Grab the shaded band anywhere off
  a package and move it; it snaps to 15 minutes. This works in the ATO timeline and in the
  mission window picker, where the slider follows the band. A window you placed stays there
  at Take off while every player flight starts inside it; otherwise it moves to your flight as
  before. You can't drag it in a focused turn, while viewing OPFOR's ATO, or once part of the
  turn has been fought.
* **[Air wing]** A new **Air Wing Setup** window for new campaigns, built around presets. For
  each base you pick a preset from a list made for that base: ships first, then airfields
  closest to farthest from the battle. You can then add more of the faction's aircraft, save
  or load the result as a config, and apply. Every faction now has its own presets, made from
  its aircraft: carrier air wings, LHA assault groups, front-line, middle and rear airfield
  wings, and off-map bombers. The 134 built-in factions get up to 17 presets each (all but the
  three without aircraft). The historical presets are listed after them. The old
  squadron-by-squadron editor is still there as **Advanced editor…**.
  [Guide](Air-Wing-Presets.md#setting-up-the-air-wing-of-a-new-campaign)
* **[Air wing]** Presets and squadrons by location. **Presets by Base...** in the Air Wing
  Configuration window fills one base from a preset made for it: carrier air wings for a
  carrier, ARG squadrons for an LHA, and front, middle or rear groups for airfields, which are
  ranked and labelled closest to farthest from the battle (`#1 Front · Gudauta (31 km from the
  battle)`). Add Squadron picks the base first and then lists only the aircraft and squadrons
  that fly from it, and squadron base boxes use the same ranked labels.
  [Guide](Air-Wing-Presets.md#presets-by-base)
* **[Intel]** The decoy call. A package sent against a site its side's picture holds as a
  decoy gets one roll before the mission is flown. The chance starts at 15% plus 35% of the
  side's ISR, gains 20% with a SEAD element in the package (most decoys don't radiate), and
  falls off with the real site's distance from the decoy; it is 0 beyond 20 km and at most 85%.
  A package that sees through the decoy attacks the real site; one that doesn't bombs the decoy.
  DCS and the combat model follow the same call: in DCS the decoys are inert vehicle groups of
  the site's own types (radars off, weapons held), and the AI's own attack tasks are pointed at
  the decoy group, with the same weapons and release settings. The
  debrief says which happened. Target marks of every flight now sit where its side believes
  the target is (the map's marker), not on the real site.
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
* **[ATO]** The turn briefing is one line above the package list (turn, phase, main push);
  **Briefing…** opens the full text in its own window.
* **[Air wing]** The Your seat squadron list follows the air wing dialog: applying a preset,
  loading a config, adding or removing a squadron or resetting updates it at once.
* **[Full turn]** FARP setup flights and air assaults flown by the combat model (before the DCS
  window, outside the bubble or after it) now take effect: the FARP is delivered, and the
  assault takes its objective when nothing defends it. Before, only what the DCS mission
  reported counted, so a FARP whose setup flight flew before the window never came up.
* **[Planner]** FAC(A): western CAS packages over the main effort take an airborne forward
  air controller (AFAC and FAC tasks in DCS, on the kneeboard with the JTACs); CAS with a FAC(A)
  overhead hits more often in the combat model.
* **[Campaign start]** Squadrons and detachments start with their aircraft, for both sides;
  nothing is bought at turn 0 (a preset's buy number is now the number deployed, and squadrons
  start full by default). Turn 0 spends the budget on ground forces.
* **[Campaign start]** Air wing presets add strategic bomber detachments at the side's off-map
  base where the campaign defines one; each preset notes its sources.
* **[Campaign start]** **Begin Campaign** asks for H-hour, the opening emphasis, the strategic
  surprise (new setting) and the pre-war reconnaissance areas. It then flies both sides'
  reconnaissance, runs the first intel round, puts the enemy in its posture (moved SAMs, emission
  control, decoys, dispersal, alert fighters) and fires blue's opening cruise missile salvo. The
  turn 1 briefing opens with the estimate and the BDA.
* **[Bubble]** In a full turn, only what you are likely to meet goes into DCS: your package,
  your tanker and AWACS, the SEAD on your route, pinned packages, enemy CAPs and alerts covering
  your route, and the packages crossing it, about 10 packages per side (**Full turn: packages
  per side in DCS**). A CAP and the raid it would fight go in together. The combat model fights
  the rest over the same time. The Your flight card and **Bubble…** say what is in and why;
  tooltips give each package's reason; the map dims the rest; the debriefing has an
  **Elsewhere during the mission** part. Aircraft of those packages still on the ramp at your
  base are parked there. Turn it off with **Full turn: only what you'd meet is in DCS**.
* **[Tools]** `resources/tools/bubble_distortion.py` fights a saved turn's window whole and
  split into bubble and rest over several seeds and compares the losses.
* **[Your seat]** Name a squadron or a mission type (the air wing step of a new campaign, or
  **Preference…** on the **Your flight** card). Each turn the commander frags you the best
  match from its plan and the card lists the next offers; **Take** moves you. The plan never
  changes for your preference. With "No preference" only your flight has a player slot.
* **[Your seat]** In a full turn the mission starts when your flight starts up; there is no
  window picker. Without a player flight, **Take off** asks whether to fast-forward the turn,
  fly an AI-only window, or go back.
* **[Mission]** AI flights past their time on target appear heading home without the
  air-to-ground weapons they dropped, with their missiles, pods and tanks.
* **[Mission]** After you quit, the flights that hadn't finished are carried on by the combat
  model from where their plans put them, then the packages planned later; the debriefing
  shows their results instead of "not flown". The plugin writes `elapsed_seconds`.
* **[Auto Planner]** New planning behaviour: **Commander flies routine lines, you plan the
  rest**. Packages can be pinned ("Keep in my mission") for the bubble.
* **[Auto Planner]** The turn briefing describes the whole period: the main push with its
  time and key packages, one line for what flies before and after it, the routine lines, and
  what the enemy is expected to do from your own intelligence.
* **[Debriefing]** **How the plan went** is split by part of the turn: the mission (DCS),
  then before and after it (combat model), each with its key packages and routine lines.
* **[UI]** The ATO list folds a 6 hour plan to one screen: each routine line is one row with
  its reliefs inside, the main push is open, and the other waves are one row per category. A
  click on the row's badge opens it; the **Fold** chip shows everything. On the map, routine
  lines are a station symbol until selected, and the timeline shades the main push.
* **[Auto Planner]** The focused turn is now the **Mission only** option (same setting, renamed),
  off by default: new campaigns plan the full 6 hour turn. A campaign saved in either model loads
  and keeps its model; changing the setting applies from the next turn. The option gets no new
  features; the 6 hour turn is where new work goes.
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
  setting off. [Guide](Air-Campaign-Planner.md#mission-only)

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
* **[Air Wing]** Air wing presets in the new game Air Wing Configuration window: US Navy carrier
  air wings (1975–2020), USMC amphibious ready groups, USAF expeditionary forces, a NATO coalition,
  and Soviet and Russian air forces. Squadrons are placed by base kind on any theater, can come
  from different countries, and their aircraft are bought from the starting budget. Skipped
  squadrons say why each aircraft was rejected. You can save your own air wing as a preset.
  [Guide](Air-Wing-Presets.md)

## Fixes

* **[Air wing]** Presets and the Air Wing Setup window only offer the faction's aircraft as its
  mod settings leave them. Without the Super Hornet mod, carrier wings take the S-3B tanker.
* **[Air wing]** The faction carrier presets now include a tanker and SH-60B Seahawks. The S-3B
  tanker's refueling priority of 0 had been read as "can't refuel", and the helicopter slot
  took the best air-assault helicopter (a CH-47F). Carrier wings now have a ship's helicopter
  slot, which prefers naval helicopters that can fly anti-ship missions.
* **[Parking]** Jets can no longer overfill an airfield that also has helicopters (Gudauta
  at 40/31). Jets were checked only against the jet spots, but helicopters may park on those
  spots too. Free parking for jets is now also limited by the base's total, so the starting
  deployment, the **+** buy button and the AI's purchases all stop at the base's capacity.
  A save already over capacity is trimmed back when it loads.
* **[Air wing]** A base preset now fits the base's parking. Squadrons are placed in order and
  each is trimmed to the spots left; one that would be left with fewer than 2 aircraft is left
  out. The row says what was trimmed, in place of a "not enough parking" warning.
* **[Debrief]** After a turn fought by the combat model, "How the plan went" lists every package
  again. The model takes each flight off its package as it lands, so the report saw empty
  packages and showed only the tanker and CAP still airborne at the end. On the PG test
  save it now lists the 4 strike packages and all 24 support packages. "AWACSs" reads "AWACS".
* **[Fast forward]** "Fast-forward the turn" from the No player flight dialog fights the whole
  turn with the combat model whatever the "Fast forward until" setting is. With any setting
  but "Simulate entire turn", the simulation stopped on its first tick (there was no player
  to wait for) and the results showed no combat at all.
* **[Planner]** A jet flying its second sortie of the turn flies with the crew of its first,
  instead of booking a fresh pilot for the seat. Squadrons ran out of pilots well before they
  ran out of aircraft: on the PG test save VFA-41's 16 pilots were all booked with 4 jets still
  free. Replanned, the same squadron flies 9 flights (22 seats) with 13 pilots and has 3 free.
  A pilot shared by two flights goes back to the squadron once both let go.
* **[UI]** Processing the mission results uses the same progress window as Take off. It shows
  the step it is on (processing the mission data, writing the debriefing, planning the next
  turn) and the time elapsed, and the app stays responsive meanwhile. It can't be cancelled:
  a turn processed halfway would leave the campaign inconsistent.
* **[Mission Generation]** An AI package that takes the decoy attacks the decoy group with its
  usual attack tasks. A bombing task on the decoy's point had the SHOEBILL Hornets release all 8
  JSOWs about 100 km out (PG, turn 3); they fell 45 km short of the decoy and the flight
  turned home.
* **[UI]** The settings window is easier to read. Each setting has its title and control on one
  row, its description in full width below in smaller type, and a divider before the next. A
  search box filters every page by title and description, and the page list shows the
  matches per page. The window opens at 1100x820.
* **[UI]** Closing the Take off or Fast-forward progress window cancels. The combat model stops
  at its next tick, and nothing after it runs: no mission generation, no waiting window. Take
  off again to resume from where it stopped. Before, closing it only hid the window; the fast
  forward and mission generation carried on and the waiting window opened anyway.
* **[UI]** The debriefing window opens at 1280x940 (at most 90% of the screen) in two columns:
  how the plan went and the after-action report on the left, the loss lists and pilots on the
  right. In one column every box was squeezed to a few lines.
* **[UI]** The mission results window grows to fit the fast-forward combat log (900 px, at
  most 90% of the screen). At its old 570 px the log squeezed the mission status rows and
  hid the log under the buttons.
* **[Combat Model]** A HARM that hits a warship wrecks its radars and silences its SAMs for six
  hours instead of sinking it. One HARM from a SEAD escort sank LOBSTER's remaining frigate in
  every fast forward to the mission window, so the anti-ship flight planned against it found
  nothing in DCS.
* **[Combat Model]** HARMs no longer sink fast attack craft. Ships whose air defense reaches
  6 km or less (guns and MANPADS: the IRGCN boats, patrol craft) were treated as radar SAMs,
  so SEAD flights' HARMs hunted their surface search radars while fast forwarding, and an
  anti-ship package flew in DCS against ships that had already been sunk. Naval SAMs (SA-N-4
  and up) are unchanged.
* **[Auto Planner]** DEAD flights carry weapons that hit a site with its radar off. A flight
  armed only with anti-radiation missiles (an EA-18G's DEAD loadout is two HARMs) no longer
  counts as a DEAD flight: against a SAM holding its emissions (Skynet's ambush) the AI had
  nothing to fire at, dropped its attack and turned home at the IP. Such squadrons fly SEAD
  escort instead, and the DEAD goes to a squadron with JSOW, JDAM or similar.
* **[UI]** The Your flight card has its own **Your flight** tab in the left panel, with the
  whole turn briefing under it (it was a headline and a **Briefing…** window), so the package
  list gets the whole height. Choosing your package on the card, or a flight on the map,
  switches back to **Packages**.
* **[Debriefing]** The plan report in the debriefing window shows the turn that was just flown.
  It was made after the next turn was planned, so it listed the next turn's packages and mission
  window, all with "no effect reported", while the kills of the mission flown were missing.
  Packages whose flights had finished and were taken off them were also dropped. Goal lines now
  say "assessed … when planned": that figure is the BDA when the package was planned, not the
  result.
* **[Mission Generation]** Anti-ship flights fire at every ship of a group. Each aircraft first
  puts one missile on each ship, then spends the rest on the group. Each ship is attacked from a
  bearing with no other ship in the way, since an anti-ship missile locks the first ship its
  seeker finds: a ship of the same group side by side, or another group's ship near the line of
  attack. Before, the whole flight's missiles went to the first ship, and a second flight's
  Harpoons sank the first group's remaining boat instead of their own target.
* **[Mission Generation]** With culling on, the mission only keeps ground units near what is
  actually in it. The culling zones are recomputed once packages outside the mission window and
  the bubble are held back, and they include the player's route. Parked untasked aircraft at
  bases far from the mission are culled (not at the player's bases, nor red's client slots), and
  missile sites are culled like other ground units unless they get fire tasks. Before, a Strait
  of Hormuz mission still spawned every red airfield's parked aircraft and missile launchers out
  to Kish and Bandar Lengeh.
* **[Auto Planner]** Only one AEW&C line per station. When the farthest friendly base was the
  carrier itself it was listed twice, and two AWACS flew side by side over it all turn.
* **[Auto Planner]** Air defense ships count as threats on a package's route. A warship's radar
  and missiles sit on one hull, which the planner's radar SAM check didn't recognise, so a
  frigate's SA-N-4 next to the route of a DEAD package through the Strait of Hormuz added
  nothing to its risk, escort or timing. Ships are weighed by their reach like land sites.
* **[Auto Planner]** Air defense ships are attacked in the suppression wave (H-hour) with the
  DEAD, and a ship whose missiles cover the way to the period's targets goes first among them.
  Before, ships were left to anti-ship strikes in a later wave, after the SEAD had flown past
  them.
* **[ATO]** The ATO timeline redraws as soon as a package's timings change (TOT, flights added
  or removed), not at the next turn.
* **[UI]** **Take off** and fast-forward show a progress dialog with the elapsed time while the
  mission is generated or the turn is resolved; before, the window froze and looked stuck.
* **[Mission Generation]** DCS no longer rejects the mission with "All waypoints have locked
  speed and surrounded by waypoints ... with locked time" for a CAP whose racetrack start is
  already behind it at mission start.
* **[Briefing]** The DCS briefing is plain text ("AEW&C", not "AEW&amp;C"). Friendly packages
  are listed by time over target, each with its flights, base and take-off time; CAP stations,
  AWACS and tankers are one line each with their times on station.
* **[Auto Planner]** Against a dense IADS (Iran 2015) blue planned no offensive packages at all:
  the rollback openers were judged on the straight-line threat, which put one SAM site inside
  the normal allowance, while every planned route was heavier. When the first offensive pass
  attacks no SAM site, the lightest ones are now opened on anyway. The SAM part of the risk
  estimate is refitted to the combat model as it is now: it was 5–12 times too high (a
  package through route SAM weight ~20 was estimated at 42% per sortie and lost 5%).
* **[Fast Forward]** CAS over the front makes 4 attack passes per aircraft and sortie, with the
  most effective weapons first, and brings the rest home. Before, every weapon went at its own
  vehicle: an A-10C pair killed 17 vehicles in one pass and a front was gone in a few turns.
  The planner's CAS estimate counts the same passes.
* **[Auto Planner]** A CAP station deep in overlapping SAM coverage is pulled back along its
  axis. Its risk estimate grew only linearly with the coverage, so a station that lost 5 of 12
  sorties in Desert Storm-like runs was estimated at 1.5% and never moved.
* **[Auto Planner]** CAS risk estimates count the ground fire of the troops at the front
  (MANPADS, AAA, small arms), and front-line attack missions go to the least exposed squadrons
  first. Before, the nearest squadron flew them, often UH-1H gunships with rockets, which lost
  about 1 in 10 sorties while estimated under 1%.
* **[Auto Planner]** Western CAS in the phases where blue holds on the ground (posture, Phases
  I and II) is sized to support the troops in contact, half of what it was; wearing the enemy
  army down starts with battlefield preparation. Before, Phase I CAS destroyed a peer front in
  three turns.

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
