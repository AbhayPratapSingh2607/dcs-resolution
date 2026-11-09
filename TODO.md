# TODO

## Focused turns: a smaller, readable air war per turn

**Goal.** A turn is the "Desired mission duration" (30–150 min), not a 6 hour air tasking
order. The main combat happens inside that window. The planner plans far fewer flights: one
CAP per threat axis instead of tens of BARCAP relays, and about 10 meaningful packages. That
keeps the realism that matters (doctrine, threat-sized packages, SEAD, GCI, intel,
attrition) and cuts the realism nobody sees (CAPs that never fight, relays, hours of
transit).

**Main goal (user, 2026-11-09): the battlefield should feel alive.** The mission opens in
the middle of an air war, not at its first takeoff. Some flights start on the ground beside
the player, some are taxiing or taking off, some are holding or on station, some are
inbound, and some are coming home from an earlier sortie. Flights keep living after the
window: they RTB and land on their own. Fewer flights, but each one visibly doing
something.

**Decisions (user, 2026-11-09):**
- Turns keep 6 h steps so day and night still cycle. Each turn is a focused window at the
  start of its step.
- The rest of each 6 h step is fully quiet: nothing is flown or simulated between windows.
- At the end of the window the mission doesn't end. The player can keep flying while AI
  flights finish on their own (RTB, land).
- About 10 packages per side per turn, as guidance, not a hard limit.
- AI flights don't all start in the air. They start at a mix of stages (F3).

**Today:**
- Each turn plans an ATO period (`ato_period_hours`, default 6 h) and DCS flies a window
  of it (`game/sim/atoperiod.py`). The combat model fights everything before and after the
  window.
- The planner sizes its plan for the whole period: CAP relays every ~55 min, HVAA CAP
  chains, second sorties.
- So a 60-minute mission sits inside a plan of 40+ packages. In the USA 1990 vs Iraq 1991
  test: 22 BARCAP packages, 6 HVAA CAP relays and 5 tanker relays.
- **Already built that this can reuse:** the On Station start type, ground alerts that
  are late activated with GCI scrambles, the combat model, and ground combat calibrated
  for one mission per turn.

### Turn model

- [ ] **F1. Add a "Focused turn" setting and make it the default.** The planning period
  becomes the mission window plus a short lead-in, and there's no separate 6 h period or
  window offset. Keep the 6 h period as the "theater" option for people who want it.
  - Every phase, apportionment and MOE that assumes 6 h (sortie counts, turnaround,
    `max_sorties_per_airframe`, CAS sizing per period) has to scale with the period
    length, or be redefined per turn.
  - **Decided:** turns keep 6 h steps, so day and night still cycle. Each turn is a
    focused window at the start of its 6 h step, and the rest of the step is fully quiet
    (see F9).
- [ ] **F2. Fit the timeline to the window.**
  - H-hour is a few minutes after mission start.
  - Every TOT falls inside the window, leaving time to egress before it ends.
  - Nothing is planned to take off after the window, so `defer_after_window` and
    `resolve_remainder` become dead code in focused mode.
  - Waves (SEAD, then strikers, then follow-up) are minutes apart, not hours. This works
    together with the H-hour sequencing in item 2 below.
- [ ] **F3. Start AI flights at a mix of stages (living battlefield).** Each AI flight
  gets a start stage that fits where it would really be at mission start, given its TOT,
  its base and the "the war started hours ago" assumption. The mix is the point: not
  everything in the air, not everything on the ramp.
  - **On the ground with the player:** cold or hot on the ramp, taxiing, or lined up.
    Packages with a late TOT from a nearby base, and ground alerts, which stay on the
    runway until GCI scrambles them.
  - **Taking off and climbing out:** flights whose takeoff falls in the first minutes of
    the window.
  - **Holding:** packages waiting at the hold or push point for their TOT, CAS stacks
    waiting for a tasking, and tankers with receivers queued.
  - **On station:** CAPs, AWACS, tanker tracks.
  - **Inbound:** strikers and SEAD between hold and target. Long-range bombers at their
    ingress point, with the hours of transit assumed; they can come from off-map bases.
  - **Returning (RTB):** flights that flew a sortie just before the window. They spawn
    egressing or on the way home with reduced fuel and expended weapons, then land. They
    are "ambience with stakes": they can still be intercepted, and losses count.
    - These are real sorties from the same air wing. The planner treats them as the end
      of the turn's earlier sortie: no target effect in this window, the airframes are
      busy, and they turn around for the next turn.
    - Keep them few (e.g. 1–3 per side), weighted to bases near the player.
  - **Player flights** keep the start type the player chose.
  - Extend On Station and the waypoint generator so every stage spawns at a consistent
    position, altitude, speed and waypoint index. For RTB, the flight starts on its
    return leg.
- [ ] **F4. Give flights that start in the air a realistic fuel state.** Base it on the
  distance from home base to the spawn point, keeping each aircraft's fuel-for-RTB rule.
  Bombers that "flew for hours" arrive with tanker-topped or reduced fuel. Check the AI
  doesn't go RTB on bingo straight away.
- [ ] **F5. Let the mission run past the window.** Decided: the mission doesn't end at
  the window end. The player keeps flying while AI flights finish their legs, RTB and land
  on their own. To do:
  - The debrief commits whatever happened, including after the window. Flights still
    airborne when the player ends the mission are assumed to recover unless damaged or out
    of fuel. That's what the fast forward does today for flights still in the air.
  - The fast forward (when the player skips the mission) resolves the same window, plus
    recovery.
  - Nothing new is scheduled after the window except ground alerts, which can still be
    scrambled. That way, flying on doesn't keep spawning fresh packages.

### Planning scale

- [ ] **F6. Make the sortie budget per turn follow the window length.**
  - Today a side has ~250 sorties per 6 h. A 60-minute window should plan roughly what
    fights in that hour, not 1/6 of the sorties spread over relays.
  - Apportionment shares stay, so doctrine still sets the mix; only the total changes.
  - Aim for about 10 packages per side per turn (decided). This is guidance, not a hard
    limit: the planner plans by priority and stops adding low-priority packages around
    the target, but can go over for something that matters (a raid, a CSAR, a GCI
    response).
    - Add a "target packages per turn" setting, default 10.
    - Packages that start in the RTB stage (F3) don't count toward it.
- [ ] **F7. Plan one CAP per threat axis for the whole window.**
  - A single flight covers the window when its endurance on station is longer than the
    window, so there are no relays.
  - HVAA CAP only where enemy fighters can actually reach the AWACS or tanker track.
  - Extra defensive depth goes to ground alert, which spawns nothing until GCI scrambles
    it.
  - This replaces most of item 4 below.
- [ ] **F8. Keep support to the minimum.** One AWACS per side, and one tanker track per
  receiver type that needs it. No relays inside the window. Carrier recovery tankers only
  when carrier aircraft fly in the window.
- [x] ~~**F9. Abstract the air war that isn't flown.**~~ Decided against: the hours
  between windows are fully quiet. Only the existing per-turn processes run between turns
  (repairs, procurement, intel decay, SAM moves, aircraft turnaround). Revisit only if
  campaigns feel too slow.
- [ ] **F10. Merge packages.** Merge small packages with nearby targets and TOTs into one
  strike package with a shared escort and a shared SEAD corridor (item 1 below). Fewer,
  bigger packages are easier to follow and need fewer escorts.
- [ ] **F11. Keep both sides at the same scale.** Red's profiles (raids, alerts, IADS
  management) follow the same window and the same caps. Raids are sized to the window, and
  the echelons of a raid are minutes apart.
- [ ] **F12. Keep the ground war and air war per turn in line.** Ground combat is already
  calibrated for one mission per turn. Check that CAS sizing (`cas_attrition` per period)
  and interdiction still match when the period is the window.

### Player comprehension

- [ ] **F13. A turn briefing.** A short plan summary at the top of the ATO panel and in
  the mission briefing:
  - phase and intent;
  - main effort;
  - the 3–5 key packages and what each is for;
  - known threats;
  - what the enemy is expected to do (only what blue's intel supports).
- [ ] **F14. A less cluttered ATO list and map.**
  - Group the list by package with the key packages first. Collapse routine DCA and
    support to one line each, e.g. "2 CAP stations, 1 AWACS, 1 tanker".
  - On the map, draw CAP stations, tanker and AWACS tracks as compact symbols instead of
    full routes, and show full routes only for the selected package.
- [ ] **F15. A unit budget for the mission.** A setting for the aircraft (and optionally
  ground units) a mission should hold, for performance. Like the package target (F6), it's
  guidance: the planner prefers fewer, better-placed flights near the budget, and the
  mission generator warns when it goes well over.
- [ ] **F16. A debrief that follows the plan.** Report each key package (goal, result,
  losses) before the full loss list.

### Living battlefield

Ways to make the window feel like the middle of a war without many more units.

- [ ] **F19. Turnaround at the player's base.** At the player's base, show the turnaround
  of the air war:
  - a flight landing as the player starts up (RTB, F3);
  - another taxiing out;
  - aircraft parked in their shelters or on the ramp. These are static, cheap, and drawn
    from the real squadron inventory, so losses and damage show.
- [ ] **F20. Radio traffic that reflects the plan.** AWACS and GCI calls for scrambles and
  picture calls, JTAC check-ins for the CAS stacks, and tanker check-ins. They come from the
  same data the planner and the GCI dispatcher use, so the radio tells the story of the
  turn. Investigate what the existing plugins (EWRS, MOOSE) can be driven with.
- [ ] **F21. Helicopters in the background.** Utility, CSAR and resupply helicopters near
  the front and the player's base. They are cheap units that read as "busy theater". This
  ties into CSAR and the dynamic FARPs. Keep them low and few, and count them in the unit
  budget (F15).
- [ ] **F22. The enemy is visibly active too.** Red's GCI scrambles, a red CAP on its
  station, red helicopters behind its lines, and SAMs shifting position between turns
  (already built). This applies the same mix of stages to red (F3, F11).
- [ ] **F23. Leftover traces of earlier turns.** Burning wrecks at struck sites (static
  carcasses already exist), craters on damaged runways, damaged SAM sites shown as
  damaged. Makes the "hours of war before this window" visible without flights.
- [ ] **F24. A small amount of randomness in timing.** Small TOT and takeoff jitter, an
  occasional flight that aborts on the ground (mission-capable rate) or comes home early,
  so the battlefield doesn't run like clockwork. This is player-visible only; planned
  effects stay deterministic enough for the planner.

### Realism kept, and how to check it

- [ ] **F17. Track aircraft availability per turn.** Sortie generation still uses
  mission-capable rates, but per window. Losses per turn will be smaller, so check:
  - whether campaigns take many more turns to reach each phase;
  - whether the phase MOEs (enemy air attrition, c2_degraded, ...) need lower thresholds,
    or need to count per day instead of per turn.
- [ ] **F18. Re-run the validation in focused mode.**
  - Run `campaign_matrix.py` and `campaign_e2e.py` with focused turns and re-check the
    bands (iraq, iran, peer, red_wins). They will need new turn counts.
  - Add matrix metrics: packages per side per turn, aircraft in the mission, and
    simulation time.
  - Do a DCS performance check on a busy theater, recording frame rate and unit count
    before and after.

### Existing features the change touches

Found by going through what the branch already does. Each one assumes today's 6 h
period, or interacts with the new starts.

- [ ] **F25. The window picker and pre-window fighting.** Today **Take off** asks which
  window of the period to fly (a 15-minute slider in `QTopPanel.py`). The combat model fights
  everything before it (`advance_to_window`) and after it (`resolve_remainder`).
  - In focused mode the window is the turn, so the slider and both of those steps go.
  - Keep them for the 6 h "theater" option.
  - The ATO timeline shows the window and the run-out after it (F5) instead of 6 h. The
    **DCS** badge on package rows is no longer needed.
- [ ] **F26. Second sorties and turnaround.**
  - Turnaround is 2 h for fighters and 4 h for bombers, longer than most windows, so
    second sorties (`sorties.py`, `max_sorties_per_airframe`) mostly disappear. Keep them
    only when the window is long enough (e.g. 150 min).
  - Returning flights (F3) take the airframes of "the earlier sortie". Count them in the
    ledger so the same aircraft aren't also tasked in the window.
  - Revisit the second-sortie fix from today (`_ground_unavailable_sorties`) under the new
    timing.
- [ ] **F27. Readiness across a 6 h step.** With ~10 packages a turn, most aircraft sit
  idle. Decide whether these work per turn or per day:
  - mission-capable rates (80%);
  - pilot limits (`max_sorties_per_pilot`);
  - repairs.

  Without that, a squadron could fly every single turn, four turns a day, without any
  fatigue.
- [ ] **F28. Economy and procurement.**
  - Income per turn stays the same, but losses per turn drop a lot, so money piles up.
  - The request for forces finds smaller shortfalls, and replacements stay at 4 aircraft
    per squadron per turn.
  - Check with the F17 data whether the AI over-buys or runs out of parking, and whether
    income or prices need scaling.
- [ ] **F29. The turn-0 plan looks like the first turn.** Before **Begin Campaign**, the
  ATO shows the pre-war "Phase 0: Posture" plan: DCA and support only. It's replanned when
  the campaign begins and never flown, but it reads as the first turn's plan (it confused
  the user on 2026-11-09). Fix one of two ways:
  - label it "Pre-war posture — replanned when the campaign begins";
  - or don't show a plan at turn 0.
- [ ] **F30. Player flights in a short window.**
  - A player starting cold on the ground needs 15–20 min before taking off. The player
    package's TOT has to leave that time, or the player gets a hot or runway start.
    Interacts with "Player missions ASAP" (`auto_ato_player_missions_asap`).
  - Player packages always count as key packages (F13), and count toward the ~10.
  - Multiplayer: player flights at several bases each get their own living base (F19)
    within the unit budget.
- [ ] **F31. Ground and sea activity in the window.** Part of the living battlefield and
  part of the unit budget:
  - convoys and transfers already moving on roads (`game/transfers.py`);
  - cargo ships;
  - airlift flights;
  - front-line units.

  Check that transfers in progress appear in the window at the right place. Count
  front-line units (front width, `perf_culling`) against the budget (F15).
- [ ] **F32. Spawning, despawning and parking.**
  - Late-activate flights whose stage starts later in the window, so the unit count at any
    moment stays low.
  - Remove AI aircraft some minutes after they land and park (including RTB flights,
    F3/F5).
  - Check parking at a busy base, where these all compete:
    - ground starts beside the player;
    - parked static aircraft (F19);
    - flights landing.
  - Check carrier deck space for ground starts and recoveries.
- [ ] **F33. CSAR, FARPs and air assault in the window.**
  - Downed pilots' survival is counted in turns, which stay 6 h, so it doesn't change.
  - CSAR packages, FARP setup and resupply flights, and air assaults aren't counted toward
    the ~10 packages.
  - They must fit the window: a FARP setup flight must land within it, or its delivery
    is counted when the player ends the mission.
- [ ] **F34. Red in DCS.**
  - Red's alerts stay late activated for the GCI plugin.
  - Skynet emission control orders still apply.
  - Red gets the same mix of start stages (F3, F22), including RTB flights near its own
    bases.
  - Red's mixed starts must not hand the player free kills on aircraft taking off. Weight
    red's ground starts to bases away from the player's package routes.
- [ ] **F35. Intel and adaptation with fewer flights.** Intel sources were tuned for 6 h
  of activity a turn:
  - satellite passes;
  - recon flights;
  - EWR and AWACS observations;
  - learned threat axes (decay 0.7 per turn);
  - ELINT from SAM engagements.

  With far fewer flights, each side sees much less per turn. Check that intel confidence
  and learned axes still build up. If not, scale the decay or the per-observation weights
  to the window.
- [ ] **F36. Save compatibility and switching modes.**
  - Campaigns started with the 6 h period must still load. Switching the setting
    mid-campaign must work, which affects:
    - `period_for`;
    - deferred packages;
    - the window offset;
    - the ATO already planned for the turn.
  - Switch at the next turn boundary only.
- [ ] **F37. Settings and docs.**
  - New settings, each with a clear description:
    - focused turns on or off;
    - target packages per turn;
    - unit budget;
    - number of returning flights;
    - start-stage mix.
  - Rewrite the planner doc sections "Sorties and timing", "Flying a window of the period"
    and "Reading the ATO", and add a "Living battlefield" section and a changelog entry.
- [ ] **F38. Tests.**
  - Unit tests for:
    - start-stage assignment (F3);
    - fitting the timeline to the window (F2);
    - the package target (F6);
    - one CAP per axis covering the window (F7);
    - nothing new scheduled after the window except alerts (F5).
  - Add a `--focused` flag to `campaign_e2e.py` and the matrix.

## Air campaign planner: Phase I offensive (Western profile)

Found 2026-11-09 in a USA 1990 vs Iraq 1991 Caucasus campaign. In Phase I, offensive
counter-air planned 0 of 54 sorties and strategic attack 0 of 37. The 12 F-15Es at
Senaki and the 4 B-1Bs got no tasks, while DCA flew 40 sorties against 30 Iraqi
fighters hiding in shelters. These items still apply with focused turns: they decide what
the few packages of a turn are.

- [ ] **1. SEAD covers a corridor, not one package.** A SEAD or DEAD flight suppresses a
  route corridor for a time window, and every package on that corridor inside the window
  counts as escorted. Today each package entering radar SAM coverage needs its own SEAD
  escort. The few SEAD-capable squadrons (F-16CM, AV-8B, Hornets) are used up by the DEAD
  packages, which caused 59 drops ("SEAD Escort: no mission-capable aircraft free in the
  sortie window"). This is also what F10 relies on.
- [ ] **2. H-hour sequencing in Phase I.**
  - First wave: DEAD against EWRs and the SAMs covering the corridors, plus strikes on
    C2 targets.
  - Second wave, 10–20 minutes later: strike and OCA packages through the suppressed
    corridors.
  - Deep airfields stay off the list until rollback has thinned the IADS. They are
    currently estimated at 18–57% losses per sortie against a 3% limit, including 5–8
    SAMs that are suspected but not located.
  - With focused turns, this is the shape of the first turn's window (F2).
- [ ] **3. Give idle strike aircraft the next-best target.** If a strike squadron would sit
  out the turn, give it the best target it can reach without a SEAD escort: targets
  outside radar SAM coverage, or interdiction and battlefield strikes near the front.
  This respects the package cap (F6).
- [ ] **4. Size DCA to the enemy's real air threat.** Scale DCA by the enemy's fighter
  numbers, its posture and the enemy sorties our radars actually saw. An enemy hiding its
  air force gets ground alerts, plus HVAA CAP only where its fighters could reach the
  AEW&C or tanker tracks. Freed sorties go to OCA and strike. Mostly covered by F7.

## Fast forward: fights restart with nothing happening

- [ ] **5. Stop fights that can't produce a shot from restarting.** In one fast-forwarded
  turn on 2026-11-09, 135 of 362 new fights were BARCAP fighters (F-14B, F-15E) against the
  red A-50 AWACS. Each ended "Air engagement over after 40s, 0 shots" and was started again
  a few seconds later. The same pattern showed up for F-15E vs Su-33 CAPs. Find out why the
  combat initiator keeps matching these flights (probably the A-50 is inside the CAP's
  commit region but outside weapons range, or the AWACS can't be engaged). Then make a fight
  that ends with no shots fired stay off for those flights for a while, or don't start it
  when no shot is possible. These restarts are what made that turn's fast forward take about
  3 minutes in the app. Focused turns make this less costly, but it's still a bug.

## OPFOR planner: open issues from tuning (step 11)

From the test matrix (`resources/tools/campaign_matrix.py`) and e2e runs on 2026-11-09.
Results: red_wins PASS (4 of 4), iraq PASS (exchange ratio 5.6–24), iran FAIL. peer passed
only a short run (3 seeds, 4 turns).

- [ ] **6. Iran: nobody fights.** In all 4 runs Iran lost 0 aircraft and blue lost 1–12.
  - After turn 1, blue plans only 2-ship packages and drops ~170 packages a turn.
  - Red flew ~170 sorties with 0 GCI scrambles and 0 SAM moves.
  - Confirm the cause before tuning. It's probably items 1–3 against a much denser IADS,
    but also check:
    - why Iran's ground alerts never scramble;
    - why its mobile SAMs never move;
    - whether blue's risk estimate is broken (next item).
- [ ] **7. Blue's risk estimate shows 0.0%.** In the iran runs, blue reports "est. risk
  0.0%" from turn 2 on while its actual losses are 2–4.3% per sortie. Find where the
  estimate drops to zero (2-ship packages, DCA-only plans, or a missing threat input).
- [ ] **8. Red CAPs get swept.** Red's standing CAPs lose badly to blue fighter sweeps
  supported by AWACS.
  - In one run, Russia 1990 lost 49 of 75 aircraft on turn 1, most of them Su-33 BARCAPs.
  - Red's DCA risk estimate said 2.6%, but losses were 65%.
  - Fix:
    - the CAP risk estimate must count enemy sweeps and escorts that can reach the
      station;
    - when the enemy sweeps, red should pull CAPs back under its SAMs or replace them
      with ground alerts. Force preservation does this today, but only after the losses.
- [ ] **9. Red client loss rate.** In the iraq runs, Iraq lost 45–71 aircraft out of
  84–99 sorties (over 50% per sortie) against a 6% risk limit. Its estimate is far too low.
  Either Iraq should fly much less (ground alerts only when outclassed), or the estimate
  should stop those sorties.
- [ ] **10. The full matrix.** Run all four scenarios at full length (8 turns × 5 seeds;
  6 turns for red_wins). Peer hasn't been run at full length, or since base captures
  became possible in fast forward. Re-run after items 1–9, and again in focused mode (F18).

## Checks in DCS (nobody has flown these yet)

- [ ] **D1. GCI scramble plugin.** A red alert pair activates when a blue package crosses
  an EWR sector, and nothing launches once the EWR is dead or jammed.
- [ ] **D2. Skynet emission control.** Dark and ambush orders behave as intended, and the
  `autonomous_behaviour` fix works.
- [ ] **D3. Low-level ingress.** Strikers with low ingress fly at about 500 ft AGL.
- [ ] **D4. Raids.** The echelons of a massed raid arrive minutes apart.
- [ ] **D5. Moved SAMs and decoys.** They appear at their new positions in DCS, while
  blue's map still shows the old position until the site is found again.
- [ ] **D6. Fast-forward base capture.** The captured base, its units and the new front
  generate correctly in the next mission.
- [ ] **D7. Mixed start stages (after F3).** Each stage spawns sensibly:
  - air starts at the right altitude, speed and next waypoint;
  - ground starts on free parking;
  - RTB flights land;
  - tankers and AWACS start their orbit task.

## Suggested order

0. **Quick fixes first:** item 5 (fights restarting with no shots), F29 (turn-0 plan
   label), item 7 (risk estimate at 0%). Small, and they make everything after easier to
   test.
1. **Turn model:** F1, F2, F6 and F7, with F25 and F26 (focused period, timeline in the
   window, ~10 packages, one CAP per axis, window picker and second sorties). This is
   where most of the reduction comes from.
2. **Mixed starts and life after the window:** F3, F4, F5, F30 and F32. This is the core
   of the "alive" goal.
3. **Packages:** items 1 and 2, then F10 (corridor SEAD, H-hour, merged packages), then
   items 6, 8 and 9 (iran, swept CAPs, client losses).
4. **Readability:** F13, F14 and F16.
5. **Living battlefield extras:** F19–F24 and F31, cheapest first (F23, F19, F24, F22,
   F31, then F20 and F21).
6. **Consequences:** F27, F28, F33–F36 (readiness, economy, CSAR and FARPs, red in DCS,
   intel, saves).
7. **Unit budget:** F15.
8. **Validation and docs:** F17, F18, F37, F38, item 10, and the DCS checks D1–D7.

**Open questions (asked, not yet answered):**
- Iran: confirm why blue stalls there first, or go straight to corridor SEAD and re-test?
- Start with the turn model (F1–F3, F6, F7), or with corridor SEAD and H-hour (items 1–2)?
- Returning flights (F3): real sorties that cost airframes and can be lost, or purely
  visual?
- F19: turnaround activity only at the player's own base, or at every friendly base?
- F20: is AWACS and GCI radio traffic wanted? It's the most work of the extras.
- F27: are readiness and pilot limits counted per turn or per day?
- OK to commit and push the TODO?
