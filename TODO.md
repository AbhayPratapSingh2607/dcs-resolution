# TODO

Read `VISION.md` first. It gives the goal, what is out of scope, the decisions and the order
of the work. Before starting an item, apply its scope test (section 8). If this file and
`VISION.md` disagree, `VISION.md` is right.

**Current milestone: M1, the 6 hour war. W1–W6 and W8 done 2026-11-10; W7 (bands) recorded
below. Next: M2, P1.**

How this file is laid out:

- **Roadmap:** the work, by milestone. One milestone at a time, in order.
- **Parked:** ideas that need the user's word before any work.
- **Checks in DCS:** the running list of what to fly, kept up to date as items land.
- **Decisions:** the short list. `VISION.md` has what each one replaces.

`TODO-earlier.md` holds the lists from before the vision review (F1 to F38, items 1 to
10). They record what was built and measured. They aren't work lists any more.

## Roadmap

Each item says what to build, where it goes and what shows it's done. "Was F14" names the
item it replaces in `TODO-earlier.md`. Every item that changes the generated mission also
gets a test on the generated mission and an entry under "Checks in DCS".

### M1. The 6 hour war (app only)

Every turn plans and fights 6 hours for both sides, with the main effort in a main push as
long as the mission. The app stays as easy to read as a focused turn is today. No culling
and no player assignment yet: the window picker stays until P4.

- [x] **W1. One turn model.** Done 2026-11-10: the setting reads "Mission only",
  `campaign_e2e.py` and `campaign_matrix.py` take `--turn-model`, 3-turn runs pass in each
  model. All new work targets the 6 hour turn. Today's focused turn
  stays as an option named "Mission only" and gets no new features.
  - Rename the setting in the UI (`focused_turns` in `game/settings/settings.py`). The
    default changes in W8, once the 6 hour plan is readable.
  - `campaign_e2e.py` and `campaign_matrix.py` get a flag to pick the model. Today they run
    whatever the default is (was F38).
  - Check that what was built for focused turns works over 6 hours: fuel for flights
    already in the air (F4), the turn briefing, the debrief, SEAD corridors, pulled-back
    CAP stations and the loss experience. Go through every place that branches on
    `atoperiod.is_focused` or `planner.focused_lead_in` (`atoperiod.py`, `briefing.py`,
    `threat.py`, `campaignstate.py`, `planner.py`, `qt_ui/atopresentation.py`; the
    scheduler takes its window from the planner and has no check of its own).
  - Done when: the tests pass, and a 3-turn e2e run finishes in each model.
- [x] **W2. The main push.** Done 2026-11-10: `Timeline.push`, `period.main_push_*` in the
  profiles, push quota per offensive category, the e2e report prints each side's push and
  their overlap. Peer, turn 1: blue 12:00–13:00 with 3 of 5 offensive packages, red 11:40–12:40
  with 2 of 3. Each commander puts the turn's main effort into one block as
  long as "Desired mission duration", with smaller waves before and after it.
  - Today `scheduler.Timeline.wave_times` spreads equal waves over the period
    (`period.wave_fractions`, four for the Western profile). New: one of them is the main
    push. It takes the phase's main effort: SEAD and DEAD first, strikes minutes later
    through their corridors, then the follow-up (was F2 and item 2, including C2 strikes in
    the first wave).
  - Where the push sits in the period is the commander's choice, set in the profile. A
    first value: about 2 hours in, so there is a war before it. At least one wave comes
    before it.
  - Each side picks its own time, from its own doctrine and picture. Red never reads
    blue's plan. The e2e report says when each push was and whether the two overlapped.
  - The DCS window picker opens on blue's main push.
  - Done when: about half of a turn's offensive TOTs fall in the main push (a first
    value), at least one wave comes before it, and a test covers both.
- [x] **W3. Red plans the same way** (was F11). Done 2026-11-10 with W2: red's routine
  lines run all period, its raids strike in its push, client and irregular profiles spread
  their packages (`main_push_share` 0.3 and 0). Checked: Iraq 1991 flies homeland air defense
  CAPs across the 6 hours; Russia 2010's push sits at +100 min.
  - Routine lines for the whole period: CAPs under GCI, and ground alerts, which are
    already held all period.
  - Raids are red's main push. Their echelons are already minutes apart.
  - Client and irregular air forces keep their small packages, spread over the period.
  - Done when: in each of the four test scenarios red's plan covers the period the way its
    doctrine says, and its raids sit in its main push.
- [x] **W4. Fold the plan in the list and on the map** (was F14). Done 2026-11-10:
  `atopresentation.folds`, `AtoGroupProxy` folding with a badge click, the Fold chip, station
  symbols for routine lines on the map (`FlightJs.routine/station`), the main push shaded in the
  timeline. The e2e report prints the folded row count.
  - List: each routine line (a CAP station, an AWACS or tanker track, an alert sector) is
    one row with its reliefs inside. The main push is open. Every other wave is one row
    that opens on a click.
  - Map: routine lines as compact station and track symbols. Full routes only for the
    selected package or wave.
  - Timeline window: it already draws a relief chain in one lane. Shade the main push.
  - Done when: the first view of a 6 hour plan fits one screen at the default window size,
    and everything else is one click away.
- [x] **W5. Briefing** (was F13). Done 2026-11-10: `TurnSummary.push/before/after`,
  "Enemy expected" from the side's own intelligence, the e2e report prints blue's briefing. The turn briefing (`briefing.turn_summary`, shown in the
  ATO panel and in the DCS mission briefing) describes the period:
  - the phase and intent;
  - the main push, with its time and key packages;
  - one line each for what flies before and after it;
  - the routine lines in one line, and the threats;
  - what the enemy is expected to do, from blue's intel only (F13's leftover).
  - Done when: the box for a 6 hour plan is no longer than today's.
- [x] **W6. Debrief by part of the turn** (extends F16). Done 2026-11-10:
  `PlanDebrief.parts` (before the mission, the mission, after it; one part for a
  fast-forwarded turn), results merged from `debriefing.remainder`. "How the plan went" gets three
  parts: before the mission, the mission, and after it. Each lists its key packages and
  sums its routine lines. B6 later adds "elsewhere".
  - Done when: a turn flown through a window shows the three parts, with the combat
    model's results for before and after.
- [ ] **W7. Bands in the new model** (was F18, and the first pass of item 10).
  - Run the four scenarios (iraq, iran, peer, red_wins) for 8 turns, 6 for red_wins, in
    the 6 hour model with the main push.
  - Record exchange ratios, bases, phases, packages per side per turn and simulation time.
  - No tuning in M1. A failed band becomes a V2 item, unless it makes the game unplayable.
  - The loss rates per sortie measured in focused turns (peer: blue 7–10%, red 18–25%)
    belong to that model. Measure again before judging them.
  - Done when: the results are recorded here.
- [x] **W8. Saves, switching and the default** (was F36). Done 2026-11-10: the turn model
  is kept per period in `AirCampaignState.focused`, so a save loads in the model it was
  planned in and a changed setting applies when the next turn is planned; **Mission only** is
  off by default. Tests in `tests/sim/test_turn_model_switch.py`.
  - Campaigns saved in either model load and keep their model.
  - Switching applies at the next turn boundary. It touches `period_for`, the held-back
    packages, the window offset and the ATO already planned.
  - Then the 6 hour war becomes the default for new campaigns.
  - Done when: a save from before M1 loads and plays a turn in each model, and a test
    covers the switch.

### M2. Your seat

You state a preference, get a flight from the real plan, and the mission is the slice
around it, before and after included.

- [ ] **P1. Preference.** The player names a squadron, a mission type, or both. One per
  campaign, and it can be changed any turn.
  - Stored with the campaign, not in the settings, because it names a squadron.
  - Set at the air wing step of a new campaign and from the "Your flight" card (P3).
  - Done when: it is saved and loaded with the campaign.
- [ ] **P2. Ranked offers.** After blue's plan is made, rank its flights for the player.
  Nothing in the plan changes (decision 4).
  - Order: the preferred squadron's flights, then flights of the preferred mission type,
    then any other flight the player can fly. Within each, the main push first, then key
    packages.
  - Only aircraft a player can fly.
  - When nothing matches, say why from the plan's own records, for example "VFA-103 isn't
    tasked this turn: its aircraft are in turnaround".
  - A pure function with unit tests.
- [ ] **P3. "Your flight" card and switching.** At the top of the ATO panel: the fragged
  flight (the top offer) with a player pilot in it, its package, target and TOT, and
  "Other flights" with the next offers. Picking one moves the player there. Putting
  yourself in any flight by hand still works and updates the card.
  - Today `auto_ato_behavior` ("Prefer player pilots") spreads player pilots over many
    flights. With a fragged flight, only that flight gets a player by default. Decide in
    this item how the old setting maps.
  - Done when: turn 1 shows a fragged flight that matches the preference when the plan has
    one, and a reason line when it doesn't.
- [ ] **P4. The mission follows your flight.** The mission starts when the earliest flight
  with a player in it starts up. This replaces the window picker (`QDcsWindowDialog`) and
  the package move (`atoperiod.align_player_packages`, was F30) in the 6 hour model.
  - `atoperiod.window` takes its start from the player flights. With no player flight,
    **Take off** asks to pick a flight or to fast-forward the turn.
  - The window's length stays "Desired mission duration". It only decides what is held
    back for after the mission.
  - Several players: the earliest startup wins, and later player flights start at their
    own time. Warn about a player flight that starts after the window.
  - Done when: picking another flight moves the mission start, and a test covers it.
- [ ] **P5. Earlier strikers heading home** (F3's leftovers). Start stages follow the
  timeline for every flight of both sides:
  - not yet started: on the ground, at its time;
  - in the air before its TOT: on its route, where the combat model put it (exists);
  - past its TOT: on its way home with its weapons expended and the fuel it would have
    left. Today it spawns with a full loadout.
  - Done when: a test on the generated mission covers the three cases.
- [ ] **P6. The fight goes on after you quit.**
  - Export the elapsed mission time: `write_state` in
    `resources/plugins/base/dcs_retribution.lua` writes it and `game/debriefing.py` reads
    it. Today only `mission_ended` is exported.
  - Flights in the mission that hadn't finished when you quit are continued by the combat
    model from that time, from where their flight plans put them. Today they are assumed
    to recover.
  - Then the packages held back for after the mission are fought to the end of the
    period, as `atoperiod.resolve_remainder` does today.
  - A mission that ended without a state file (a crash) is treated as flown to the end of
    the window.
  - Done when: after quitting 20 minutes in, the debrief gives later packages results from
    the combat model instead of "not flown". Test with a made-up state file.
- [ ] **P7. Planning by hand.** The second way to play.
  - A new value between "commander plans everything" and "commander plans nothing": the
    commander flies the routine lines and you plan the rest. Today `auto_ato_behavior`
    set to Disabled stops all of blue's planning. Red is always planned by its commander.
  - Packages made by hand are key packages in the briefing and the debrief.
  - Any package can be pinned "keep in my mission" (B3 uses it).
  - Done when: a strike planned by hand shows in the briefing, and in the debrief with its
    result.

### M3. The bubble

DCS holds only what you are likely to meet. The rest of the war is fought at the same
time.

- [ ] **B1. Relevance.** For each flight of both sides: how likely you are to meet it
  during the mission (was F22, part of F34).
  - Inputs: where its flight plan puts it, minute by minute, during the mission; the
    route, target and base of every flight with a player; for red CAPs and alerts, whether
    their commit region or sector covers that route.
  - Output: a score and one reason ("crosses your route at 10:42", "CAP over your
    target").
  - Ground units keep their own culling (`perf_culling`).
  - A pure function with unit tests.
- [ ] **B2. Clusters.** Flights that would fight each other during the mission go in or
  out together: a package with its escort and SEAD, a CAP with the raid it would commit
  on, an alert pair with the raid that would launch it.
  - Predict the pairs from the combat model's own rules (commit regions, GCI sectors) and
    the flight plans, for the mission's time only.
  - Follow one step of "would fight", not the whole chain, or everything joins one
    cluster.
- [ ] **B3. Budget** (was F15). About 10 packages per side in DCS. The "packages per side"
  setting becomes this budget. It is guidance, not a hard limit.
  - Always in, outside the budget: your package, your tanker and AWACS, the SEAD corridor
    you fly through, and pinned packages.
  - Fill the rest by cluster score.
  - Warn when the aircraft count goes well over a set number.
- [ ] **B4. Generate the bubble only.** Packages outside the bubble are held back from the
  .miz the way `atoperiod.defer_after_window` holds back later packages, with the reason
  kept ("elsewhere" or "after").
  - Alert pairs in the bubble stay late activated for the GCI plugin.
  - Done when: a test on the generated mission finds only bubble flights in it.
- [ ] **B5. Fight the rest.** The combat model fights the flights outside the bubble over
  the mission's own time, then carries on with P6. The results are committed with the
  debrief (`MissionResultsProcessor.commit_resolved_period`).
  - The bubble and the rest don't interact. B7 measures what that costs.
- [ ] **B6. Show it.**
  - List: "In your mission" first, each flight with its reason. "Elsewhere" folded.
  - Map: bubble flights drawn, the rest dimmed.
  - Debrief: an "Elsewhere" part.
- [ ] **B7. Measure the distortion without DCS.** A tool that fights the same turn twice
  with the combat model, once whole and once split into bubble and rest, over several
  seeds. It compares losses and target results per side.
  - Set the tolerance from the first measurements and add the number to the matrix.
  - This matters more because nothing is flown in DCS until M6.
- [ ] **B8. Your base is alive** (was F19). At the base you fly from, and only there:
  - parked aircraft as statics, taken from the squadrons' real inventory, inside the
    aircraft count of B3;
  - arrivals and departures come from the timeline by themselves.
  - Check parking with ground starts and landings at a busy base (F32).

### M4. Campaign start

A new campaign starts the way a real operation would: a deployed air wing, a prepared
enemy, an opening salvo and a BDA. M4 doesn't depend on M1 to M3 and can be moved earlier
if the user asks.

- [ ] **T1. One branch with everything.** Merge `combat-resolution` into `Resolution`,
  which has the presets, and run the tests there. Decide where the items that need both
  the presets and the planner are built (T3, T9).
- [ ] **T2. Start with aircraft.** Squadrons and detachments start with their aircraft, for
  both sides. Nothing is bought at turn 0.
  - Presets: `buy_preset_aircraft` goes. A squadron's `buy` number becomes the number
    deployed, so a detachment starts with a few aircraft and a squadron with all of them.
  - An air wing built by hand starts full ("squadrons start full" on by default).
  - The planner's request for forces starts on turn 1. Replacements are bought as today.
  - Retune the starting budget, which now pays for ground forces only.
  - Done when: a campaign started from a preset shows no aircraft purchase at turn 0 for
    either side.
- [ ] **T3. Bomber detachments.** Where the campaign defines an off-map base for the side,
  the preset adds a detachment of strategic bombers there, never at an airfield in the
  theater. Elsewhere it adds none.
  - 10 of the 70 campaigns define an off-map base for blue. One of them (`black_sea`) also
    defines one for red.
  - The bombers enter at the map edge, as off-map flights do today.
  - Done when: bombers appear only in those campaigns, and the planner tasks them.
- [ ] **T4. Presets from real deployments.** Check the 12 presets against the deployments
  they name: squadron counts, types, and detachment sizes for AWACS, tankers, electronic
  warfare and reconnaissance. Note each source in the file. List the factions and eras
  that have no preset.
- [ ] **T5. Pre-war reconnaissance.** Before **Begin Campaign**, each side has a number of
  reconnaissance tasks to spend on areas of the map. Each raises what the side knows
  there, through the intel picture. Red's commander spends its own.
- [ ] **T6. First intel round.** At **Begin Campaign** the strategic intel round
  (`warstate._strategic_intel`) runs once, after T5, and the turn 1 briefing opens with
  its estimate. Today the pre-war picture is filled in when first needed.
- [ ] **T7. Opening choices.** At turn 0 the player picks:
  - H-hour: which 6 hour period of the day the war starts in;
  - the opening emphasis: air defenses, airfields, command and control, or balanced. It
    weights the turn 1 target list and the missile strikes (T9).
- [ ] **T8. Red's turn 0.** A new-campaign setting for strategic surprise: none, partial
  or full. It sets red's posture at H-hour: SAMs moved or still at their known sites,
  emission control, decoys, aircraft dispersed or parked in the open, and the share of
  fighters on alert.
- [ ] **T9. Opening missile strikes.** Blue only, turn 0 only (decision 5).
  - Salvo size: from the faction and its era, raised by the cruise missile ships and
    bomber detachments in the campaign.
  - Targets: fixed targets from the commander's target list, weighted by the opening
    emphasis.
  - The app resolves them at **Begin Campaign**. Hit chances depend on the target, red's
    defenses and surprise. There is no missile stock afterwards.
- [ ] **T10. Turn 1 BDA** (was F23). Turn 1 opens with a BDA report: what was fired at and
  what intelligence assesses was hit, with the intel picture's uncertainty. The damage
  shows on the map, and in the first mission as wrecks and craters.
  - Done when: the report changes with the surprise setting and the opening emphasis.

### M5. Realism and balance

- [ ] **V1. Full test matrix, campaign pace and economy in the new model** (was item 10,
  F12, F17, F28).
  - All four scenarios at full length: 8 turns × 5 seeds, 6 turns for red_wins.
  - Turns per phase, and whether the phase thresholds still fit.
  - Whether money piles up or the AI over-buys.
  - Whether CAS and interdiction still match the ground model.
- [ ] **V2. Planner leftovers.** Only where a band fails or a symptom is named, one at a
  time:
  - idle strike aircraft get the next-best target (item 3);
  - DCA sized to the enemy's real air threat (item 4);
  - a CAP station's estimate counts the enemy sweeps that can reach it (item 8);
  - client alert sectors pulled under the SAM umbrella (item 9);
  - why Iran's ground alerts rarely scramble (item 6).
- [ ] **V3. FAC(A) line.** A routine line over each active front: a FAC(A) flight for the
  period that marks targets for CAS. There is no FAC flight type today. First check what
  the DCS AI can do with its FAC task.
- [ ] **V4. CSAR, FARP and parking in the period** (was F33, F32). CSAR packages, FARP
  setup and resupply flights and air assaults in a 6 hour turn and in the bubble, and
  parking at busy bases and on carrier decks.
- [ ] **V5. Docs and tests** (was F37, F38). Rewrite the planner guide for the turn model,
  the main push, your flight and the bubble. Settings descriptions and the changelog.

### M6. The DCS pass

Every open item under "Checks in DCS", flown in one pass (decision 8). Then the fixes,
then a frame rate and unit count measurement on a busy theater.

## Parked

These need the user's word before any work. Don't build or propose them as part of a
milestone.

- **F27, readiness per turn or per day.** Shelved. A 6 hour war four times a day makes it
  matter more, so it's worth a second look after M1.
- **F10** merging packages, **F21** background helicopters, **F24** timing randomness,
  **F31** ground and sea activity in the mission, and stand-off SEAD.
- **Turn 0 ideas** suggested on 2026-11-09 and not decided:
  - forces that arrive over the first turns instead of all at once;
  - a weather and light forecast for the first day, to inform H-hour;
  - a logbook for your pilot (today a pilot's record is only missions flown);
  - CAP stations and tracks that keep their names from turn to turn;
  - limited stocks of precision weapons;
  - special forces or cyber actions before H-hour;
  - target restrictions that lift as the phases advance.

"Not doing" is in `VISION.md`, section 4. Radio chatter (F20) is on it.

## Checks in DCS (nobody has flown these yet)

The running list of what to check in DCS. Add an item whenever a feature that changes the
generated mission lands, and tick items once they're flown. Report problems with
`Saved Games\DCS\Logs\dcs.log` or a Tacview recording.

**Decided 2026-11-09:** these are flown in one pass at the end (M6), not after each
milestone. So every item that changes the mission also gets a test on the generated
mission.

D7's two returning CAPs and all of D9 describe the **Mission only** option (off by
default since W8). D11 checks the 6 hour turn.

**Setup:**
- A campaign with blue against a modern Russian faction. Russia's planner profile uses
  ground alerts, massed raids, SAM emission control and SAM moves. Use a Soviet-era faction
  for the low-level check (D3).
- Fog of war off (Settings → Campaign doctrine), so the app shows red's ATO to compare
  with DCS.
- Plugins (Settings → Plugins): **GCI ground alert scrambles** on, with its `announce` and
  `debug` options on, and **Skynet IADS** on.
- Tacview helps. The GCI plugin's debug output goes to `dcs.log`.

- [ ] **D1. GCI scramble plugin.**
  - In the app, find red BARCAP packages named "Alert \<base\>".
  - Send or fly a blue package toward that base, inside red early warning radar coverage.
  - **Expect:**
    - the alert pair appears and takes off when the package is detected; it's late
      activated, so it isn't visible before;
    - an announce message, and the scramble shown in `dcs.log`;
    - no more pairs per raid than the doctrine allows (2 for Russia);
    - pairs that are never scrambled stay hidden all mission;
    - (added 2026-11-09) a raid far bigger than the alert aircraft in its sector gets
      nothing scrambled: more than 3× for Russia, 2× for client air forces such as Iraq,
      and less under force preservation. With the plugin's debug option, `dcs.log` says
      "raid of N too strong".
  - Then kill red's early warning radars (or test where they don't cover) and repeat.
    Nothing should launch.
- [ ] **D2. Skynet emission control.** Find SAMs set to ambush or dark (the app's air
  campaign page, IADS orders). **Expect:**
  - ambush sites stay off your radar warner until you're close, then fire;
  - dark sites stay silent;
  - active sites radiate normally;
  - no Skynet errors in `dcs.log`, especially about `autonomous_behaviour`, which was
    fixed on this branch.
- [ ] **D3. Low-level ingress.** With a Soviet-era red, red strikers fly ingress and egress
  at about 500 ft above ground (Tacview).
- [ ] **D4. Raids.** Russian or Soviet red in its initial air operation phase plans raids;
  its packages share a raid id, shown in their planning details. **Expect** them to arrive
  in this order, minutes apart:
  1. suppression, about 8 minutes before the strike;
  2. fighter sweep, about 4 minutes before;
  3. main strike group;
  4. follow-up group.
- [ ] **D5. Moved SAMs and decoys.** After a turn where a red mobile SAM fired, the turn's
  report lists the red SAM moves. **Expect:**
  - with fog of war on, your map still shows the site at its old position;
  - in DCS it's at the new one (F10 map with all units shown, or Tacview);
  - decoys sit near the radar SAMs.
- [ ] **D6. Fast-forward base capture.** Fast-forward until a front collapses and a base
  changes hands (red against a weak blue gets there in a few turns). Then generate and fly
  the next mission. **Expect:**
  - the base belongs to its new owner, with the new owner's units and a new front line;
  - no errors when the mission loads.
- [ ] **D7. Mixed start stages (F3, F4).** In a focused turn, look at the F10 map at mission
  start and in Tacview. Each stage spawns sensibly:
  - two CAPs per side named "CAP …" with the note "Returning from the previous CAP shift"
    are in the air heading home and land; they shouldn't turn back to their station;
  - flights that took off during the lead-in are on their route, not over their base;
  - AI flights already airborne don't go bingo or RTB straight away (fuel F4), and their
    fuel looks plausible in the F10 unit info (less than full for most);
  - air starts at the right altitude, speed and next waypoint;
  - ground starts on free parking;
  - RTB flights land;
  - tankers and AWACS start their orbit task.
- [ ] **D11. The 6 hour turn (default).** Settings → Campaign management: **Mission only** is
  off. Pass a turn, then press **Take off**. **Expect:**
  - the window picker opens with the slider already on blue's main push (the briefing above
    the package list names the push's time, and the timeline shades it in amber);
  - the ATO list is folded: CAP, AWACS, tanker and ground alert lines are one row each with a
    ▸ badge, strike packages before and after the push are one row per category, and the push's
    packages are open; the Fold chip shows the count;
  - on the map, CAP stations and tanker and AWACS tracks are small dashed circles; selecting one
    in the list draws its route;
  - in DCS, flights that took off before the window are in the air on their routes, later
    flights are on the ramp at their time, and the mission briefing reads "Turn N: ..., main push
    HH:MM-HH:MM";
  - after the mission, the debriefing's **How the plan went** has three parts: the mission,
    before it and after it.
- [ ] **D9. Mission only (Settings → Campaign management, off by default).** Turn it on, pass
  a turn and generate the mission. **Expect:**
  - **Take off** goes straight to the mission, with no window picker;
  - the mission starts 30 minutes after the turn's start time (the lead-in), and the
    combat model fights those 30 minutes first;
  - flights that took off during the lead-in are in the air on their route, not at their
    base; flights that take off later are on the ramp;
  - every package's TOT falls inside the mission (the ATO list's TOT column);
  - each CAP stays on station until about the end of the mission; there are no reliefs
    arriving in the last minutes;
  - about 10 combat packages per side, plus AWACS, tankers and ground alerts.
  - Put yourself in a package whose takeoff falls in the lead-in (ATO list: its offset is
    negative). On **Take off** the package moves later: you start at mission start with
    your chosen start type, not in the air.
- [ ] **D10. Parking cleanup plugin.** Settings → Plugins: **Parking cleanup** is on (turn
  on its debug option). Watch an AI flight land at an airfield and on a carrier.
  **Expect:**
  - about 10 minutes after it shuts down it disappears, and `dcs.log` shows
    "ParkingCleanup - … removed from parking";
  - your own aircraft and helicopters stay;
  - after the mission, the debriefing does **not** list those aircraft as lost, and the
    squadron still has them.
- [ ] **D8. Things that already existed, worth checking while in DCS.**
  - **On Station:** CAPs, AWACS and tankers set to On Station appear on their tracks at
    mission start.
  - **Ground alerts:** red has fewer BARCAPs in the air than before, since part of its
    defense is now on ground alert.

**Checked in the app (no DCS needed):**
- [ ] **A5. Turn briefing.** From turn 1, a box above the package list summarizes the turn:
  phase, mission time, intent, key packages with their purpose, routine lines, threats.
  Assign yourself to a package: it moves to the top marked "(you)" after the next update.
- [ ] **A6. Debrief that follows the plan.** After a turn (fast forward or DCS), the
  debriefing window starts with **How the plan went**. Each key package shows its goal and
  result, with losses in red and unflown packages in grey, then one line for the CAP
  stations and support. Check that a SAM site you destroyed shows "target destroyed".
- [ ] **A4. Turn model settings.** Settings → Campaign management shows **Mission only**
  (off), its lead-in and packages-per-side guidance. Turn it on and pass a turn: the next turn
  plans 1.5 hours, with no window picker. Turn it off again and pass a turn: the 6 h period,
  the main push and the window picker come back. A save made in either model loads and shows
  the model it was planned in until the next turn.
- [ ] **A2. Pre-war note.** Create a new campaign: above the package list, an amber note
  says the pre-war posture plan is never flown. It disappears after Begin Campaign.
- [ ] **A3. Fast forward speed.** Fast-forwarding a turn with CAPs near an enemy AWACS
  should be noticeably quicker than before. The log no longer shows the same air
  engagement ("0 shots") restarting every few seconds.
- [ ] **A1. Fog of war map refresh.**
  - With fog of war on, switch it off in Settings: red routes and sites appear right away,
    with nothing still marked "not confirmed".
  - Switch fog of war back on while the enemy's ATO is shown: the list switches back to
    yours.

## Decisions

The full list, with what each decision replaces, is in `VISION.md`, section 5. Only the
user changes a decision.

**Decided 2026-11-09, vision review (user):**

1. Every turn is a full 6 hour air war. The combat model fights what DCS doesn't show.
2. The plan is as big as the air wing can fly. DCS gets about 10 packages per side, the
   ones near the player.
3. Two ways to play: the commander plans, or you plan by hand.
4. Your preference never bends the plan.
5. Opening missile strikes are blue only and turn 0 only.
6. Strategic bombers only where the campaign defines an off-map base.
7. Turn 0 gains red's turn 0, the opening choices and pre-war reconnaissance. No campaign
   brief.
8. The DCS checks are flown in one pass at the end.
9. Squadrons and detachments start with their aircraft. None are bought at turn 0.

**Decided 2026-11-09, earlier (user):**

- Returning flights (F3) are real sorties, planned by the planner.
- F19 only at the player's base.
- F20 (radio chatter) not implemented.
- F27 (readiness) shelved.
- The Iran stall was resolved by item 6 (openers and loss experience).
