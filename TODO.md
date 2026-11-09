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

- [x] **F1. Add a "Focused turn" setting and make it the default.** Done 2026-11-09:
  **Focused turns** (on by default) and **Focused turns: lead-in** (30 min) in Settings →
  Campaign management. The period is lead-in + mission duration; the DCS window starts when
  the lead-in ends, there's no window picker, and flights that took off during the lead-in
  are fought into place by the combat model and spawn in the air. Peer test, 60 min: blue
  25 → 12 packages, red 29 → 15; Iraq: blue 35 → 12. Still open: the sortie ledger's
  turnaround and `max_sorties_per_airframe` (F26), and CAS sizing per period. The planning period
  becomes the mission window plus a short lead-in, and there's no separate 6 h period or
  window offset. Keep the 6 h period as the "theater" option for people who want it.
  - Every phase, apportionment and MOE that assumes 6 h (sortie counts, turnaround,
    `max_sorties_per_airframe`, CAS sizing per period) has to scale with the period
    length, or be redefined per turn.
  - **Decided:** turns keep 6 h steps, so day and night still cycle. Each turn is a
    focused window at the start of its 6 h step, and the rest of the step is fully quiet
    (see F9).
- [ ] **F2. Fit the timeline to the window.** Partly done 2026-11-09: in a focused turn,
  strike TOTs fall between H-hour (`period.h_hour_min`, 5 min after the window opens) and
  `period.window_egress_min` (15 min) before it closes, with the waves spread over that
  span. Still to do: wave sequencing minutes apart (with item 2).
  - H-hour is a few minutes after mission start.
  - Every TOT falls inside the window, leaving time to egress before it ends.
  - Nothing is planned to take off after the window, so `defer_after_window` and
    `resolve_remainder` become dead code in focused mode.
  - Waves (SEAD, then strikers, then follow-up) are minutes apart, not hours. This works
    together with the H-hour sequencing in item 2 below.
- [ ] **F3. Start AI flights at a mix of stages (living battlefield).** Mostly done
  2026-11-09:
  - The lead-in (F1) already gives the mix. Peer test, at mission start, per side: ~16
    flights inbound or transiting, 4–5 waiting to start up, 2–3 taxiing, 1 taking off, 2 on
    a CAP racetrack, 1 holding, 2 on ground alert, and sometimes one already engaged.
  - **Returning flights:** each side plans 2 CAPs (`period.returning_flights`) that flew
    the shift before. They leave station 5 minutes before the mission starts and are on
    their way home ("Flying to LANDING") when it opens. They're real sorties: airframes
    claimed, fought on the way home, losses count. The part of the shift before the turn
    starts is moved along without combat (`Flight.returning`, as On Station does); the
    end of the shift, in the lead-in, is fought. They don't count toward the package
    guidance.
  - Still to do: returning strikers (with weapons expended), weighting returning flights
    toward the player's base, long-range bombers spawning at their IP after hours of
    assumed transit (today a package from a far base just gets a later TOT, or none).
    Player flights keep their start type (F30).
  Original plan: each AI flight
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
- [x] **F4. Give flights that start in the air a realistic fuel state.** Done
  2026-11-09 (`game/ato/flightstate/airbornefuel.py`): AI flights airborne at mission
  start used to spawn with full internal fuel (only player flights got the estimate). They
  now get the estimate, but never less than 1.3 × the fuel for the rest of their plan plus
  25% of a full load. External tanks still spawn full. Aircraft without fuel consumption
  data keep a full load, except returning flights, which get 40%. Base it on the
  distance from home base to the spawn point, keeping each aircraft's fuel-for-RTB rule.
  Bombers that "flew for hours" arrive with tanker-topped or reduced fuel. Check the AI
  doesn't go RTB on bingo straight away.
- [x] **F5. Let the mission run past the window.** Checked 2026-11-09: nothing is planned
  to take off after the window (F1, F2), the DCS mission doesn't end at the window, the
  fast forward runs the period plus 45 minutes of recovery, and flights still airborne
  when you end the mission are assumed to recover, as before. Decided: the mission doesn't end at
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

- [x] **F6. Make the sortie budget per turn follow the window length.** Done 2026-11-09:
  **Focused turns: packages per side (guidance)**, default 10. Once a side has that many
  combat packages, further OCA, SEAD, strike, interdiction and CAS packages are dropped
  ("packages per turn reached" in the scrub list). Ground alerts, AEW&C, tankers and HVAA
  CAPs don't count; CSAR, enablers and DCA are planned first, and raids may go over. The
  sortie total itself already follows the shorter period.
  - Today a side has ~250 sorties per 6 h. A 60-minute window should plan roughly what
    fights in that hour, not 1/6 of the sorties spread over relays.
  - Apportionment shares stay, so doctrine still sets the mix; only the total changes.
  - Aim for about 10 packages per side per turn (decided). This is guidance, not a hard
    limit: the planner plans by priority and stops adding low-priority packages around
    the target, but can go over for something that matters (a raid, a CSAR, a GCI
    response).
    - Add a "target packages per turn" setting, default 10.
    - Packages that start in the RTB stage (F3) don't count toward it.
- [x] **F7. Plan one CAP per threat axis for the whole window.** Done 2026-11-09: a CAP
  in a focused turn stays on station until the window ends (`dca.max_patrol_min` 90,
  `min_patrol_min` 20), AEW&C and theater tankers stretch their time on station by up to
  half again, no relief is planned for a gap under `period.min_relief_gap_min` (15 min), HVAA
  CAP stops at the window end, and stations within 10 nm of each other are merged. HVAA CAP
  was already only planned where enemy fighters can reach the orbit.
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

- [x] **F25. The window picker and pre-window fighting.** Done 2026-11-09: in a focused
  turn there's no picker, and nothing is planned after the window, so `defer_after_window`
  and `resolve_remainder` find nothing to do. `advance_to_window` stays: it flies the
  lead-in. The ATO list and timeline count offsets from mission start ("-0:10" is in the
  lead-in), the **DCS** badge and the "outside the DCS window" dimming are gone, and the
  timeline runs on to the last landing. Today **Take off** asks which
  window of the period to fly (a 15-minute slider in `QTopPanel.py`). The combat model fights
  everything before it (`advance_to_window`) and after it (`resolve_remainder`).
  - In focused mode the window is the turn, so the slider and both of those steps go.
  - Keep them for the 6 h "theater" option.
  - The ATO timeline shows the window and the run-out after it (F5) instead of 6 h. The
    **DCS** badge on package rows is no longer needed.
- [x] **F26. Second sorties and turnaround.** Checked 2026-11-09: with a 90-minute period
  the ledger gives one sortie per airframe (turnaround 2 h is longer than the period), and
  the focused e2e runs planned 0 second sorties. A 150-minute window can still reuse a
  helicopter (1.5 h turnaround). Counting returning flights' airframes moves to F3.
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
- [x] **F29. The turn-0 plan looks like the first turn.** Done 2026-11-09: at turn 0 the
  ATO panel shows "Pre-war posture: this plan is never flown. Begin Campaign plans turn 1,
  when hostilities start." Before **Begin Campaign**, the
  ATO shows the pre-war "Phase 0: Posture" plan: DCA and support only. It's replanned when
  the campaign begins and never flown, but it reads as the first turn's plan (it confused
  the user on 2026-11-09). Fix one of two ways:
  - label it "Pre-war posture — replanned when the campaign begins";
  - or don't show a plan at turn 0.
- [ ] **F30. Player flights in a short window.** Partly done 2026-11-09: on **Take off**
  in a focused turn, a package whose player flights would start up during the lead-in is
  moved later as a whole (`atoperiod.align_player_packages`), so players start at mission
  start with their chosen start type and the combat model never flies them. The TOT moves
  by the same amount, so it can end up late in the window. Still to do: the planner should
  leave that time when it plans packages with player slots; counting player packages as
  key packages (F13).
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

- [x] **5. Stop fights that can't produce a shot from restarting.** Done 2026-11-09: after
  an air engagement with no shots fired, the same opposing pairs of flights don't start
  another one for 5 minutes (`QUIET_ENGAGEMENT_COOLDOWN` in `model/engine.py`). SAM
  engagements are unchanged on purpose: the model is calibrated so that time spent inside
  a SAM zone is what costs aircraft. Original report: In one fast-forwarded
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
  - **Cause found (2026-11-09): the rollback never starts.** On turn 1 blue scrubbed 114
    packages for "expected attrition above the limit" and planned no SEAD, DEAD, OCA or
    strike.
    - The cheapest DEAD target in Iran's IADS still has a route SAM weight of 11 or more,
      so its estimate is 14–20% per sortie against a 4.5% limit. Deeper targets are
      30–75%.
    - The rollback allowance (up to 10% for DEAD on the outer layer) only applies at a
      route SAM weight of 8 or less, so it never applies against a dense modern IADS.
    - The result is a deadlock: no target is ever acceptable, so the IADS is never
      thinned.
  - **Possible fixes, to decide on:**
    - "The rollback has to start somewhere": when no IADS target is within the limits,
      allow DEAD on the least-defended SAMs up to the rollback limit, sized by the IADS
      rather than a fixed weight of 8.
    - Stand-off SEAD: ARM shooters that fire from outside the MEZ shouldn't be charged
      the full route SAM weight. The risk model counts the whole route through coverage
      today.
    - Corridor SEAD (item 1), which concentrates suppression on one route.
  - Still to check: why Iran's ground alerts never scramble and its SAMs never move. Both
    are probably because blue never sends anything offensive to react to.
- [x] **7. Blue's risk estimate shows 0.0%.** Fixed 2026-11-09:
  - DCA packages are now estimated and gated (risk kind "defense"). Before, they had no
    estimate at all, so a turn of only CAPs averaged to 0%. The e2e report says how many
    packages were estimated and weights the mean by sorties.
  - The CAP estimate counts SAM sites within 15 nm of the station (`packages.
    station_margin_nm`) at reduced weight, and uses its own fitted exposure
    (`risk.model.station_exposure` 0.04): Iran CAPs now estimate 3.6–3.8% against 2–4.3%
    actual. The strike fit gave ~60%.
  - CAPs no longer get SEAD escorts added by the "one more try" step.
  - Not done: pulling stations back from suspected coverage (the estimate now allows
    them), and enemy sweeps in the CAP estimate (item 8). In the iran runs, blue reports "est. risk
  0.0%" from turn 2 on while its actual losses are 2–4.3% per sortie.
  - **Cause (2026-11-09):** from turn 2 blue only plans DCA, about 46 BARCAP sorties a
    turn (item 6). A CAP's risk is estimated for its route, against the SAMs blue knows
    about, so a station placed "outside SAM coverage" estimates 0%.
  - The losses are all to SAMs while on station: CAPs orbiting for hours near an IADS
    blue hasn't fully located.
  - **Fix:**
    - estimate a CAP's risk for the time it spends on station, including the allowance
      for unlocated SAMs near the station;
    - keep stations further from suspected coverage.
  - Also count enemy fighters that can reach the station (item 8).
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
- [ ] **Focused turns raise the loss rate per sortie.** First focused e2e runs (2 turns,
  2026-11-09): peer blue 7.4–9.7% and red 18–25% per sortie, against limits of 2% and 4%;
  Iran red 23–29%. Part of this is arithmetic: the idle CAP sorties that used to dilute the
  rate are gone. The rest is items 8 and 9 (CAPs swept, red estimates too low). Judge the
  bands per turn as well as per sortie (F17, F18) before tuning risk constants.
- [ ] **10. The full matrix.** Run all four scenarios at full length (8 turns × 5 seeds;
  6 turns for red_wins). Peer hasn't been run at full length, or since base captures
  became possible in fast forward. Re-run after items 1–9, and again in focused mode (F18).

## Checks in DCS (nobody has flown these yet)

The running list of what to check in DCS. Add an item whenever a feature that changes the
generated mission lands, and tick items once they're flown. Report problems with
`Saved Games\DCS\Logs\dcs.log` or a Tacview recording.

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
    - pairs that are never scrambled stay hidden all mission.
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
- [ ] **D9. Focused turn (default for new and loaded games).** Generate a turn-1 mission.
  **Expect:**
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
- [ ] **D8. Things that already existed, worth checking while in DCS.**
  - **On Station:** CAPs, AWACS and tankers set to On Station appear on their tracks at
    mission start.
  - **Ground alerts:** red has fewer BARCAPs in the air than before, since part of its
    defense is now on ground alert.

**Checked in the app (no DCS needed):**
- [ ] **A4. Focused turn settings.** Settings → Campaign management shows **Focused turns**,
  its lead-in and packages-per-side guidance. Turn it off and replan (or start a new turn):
  the 6 h period and the window picker come back.
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

## Suggested order

0. ~~**Quick fixes first:** item 5, F29, item 7.~~ Done 2026-11-09.
1. **Turn model:** ~~F1, F6, F7, F25, F26~~ done; F2 partly. Was: F25 and F26 (focused period, timeline in the
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
