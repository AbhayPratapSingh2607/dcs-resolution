# Vision, scope and roadmap

This file says what Resolution is meant to become, what is in and out of scope, and the
order of the work. `TODO.md` lists the items. This file says why they exist and in what
order. If the two disagree, this file is right and `TODO.md` gets fixed. `TODO-earlier.md`
keeps the lists from before this file was written, as a record of what was built.

Before starting any item, read the principles (section 1), "Not doing" (section 4) and the
current milestone (section 6), then apply the scope test (section 8).

Written 2026-11-09 from the user's vision statement and the decisions taken that day
(section 5).

## 1. Vision

Turn DCS Retribution into a living war simulator where you fly as one cog in the machine.
An AI commander on each side plans a realistic air campaign. The war is fought for all
6 hours of every turn, whether or not DCS is running. The DCS mission is the slice of that
war around your flight.

**Principles.** A change either follows these or it doesn't.

1. **The war is bigger than the mission.** Each turn is 6 hours of air war for both sides,
   fought by the combat model. DCS shows the part around you.
2. **You are the center of the mission, not of the world.** The mission is built around
   your flight. The plan is never changed to suit you.
3. **The DCS experience comes first.** The app exists to give the most realistic DCS combat
   possible. Work the player sees or feels, in DCS or in the debrief, goes before work that
   only changes numbers between the two AIs.
4. **Both commanders are real.** Blue and red each plan by their doctrine, from their own
   intelligence, through phases: OCA, SEAD and DEAD first, then strike and CAS.
5. **Easy to read.** A bigger war must not mean a busier screen. The app shows your part
   first and folds the rest.
6. **Two ways to play, one war.** The commander plans and frags you a flight, or you plan
   packages by hand. Both happen inside the same 6 hour war.
7. **Existing campaigns keep working.** Nothing here needs a change to a campaign file.

## 2. The flow

What a campaign looks like when this is done, and where each step stands today.

| # | Step | Today | Milestone |
|---|------|-------|-----------|
| 1 | **New campaign.** Pick a campaign, both factions, mods and settings. | Exists | |
| 2 | **Air wing.** Build your own, or pick a preset taken from a real deployment. The preset reads the campaign's bases: a carrier gets its air wing, an LHA its Marine squadrons, an off-map base its bomber detachment. | Partly. 12 presets exist, but only on the `airwing-presets` and `Resolution` branches. No bomber group. | M4 |
| 3 | **Starting aircraft.** Squadrons and detachments start with their aircraft. A detachment starts with as many as would really deploy. Nothing is bought. | Partly. "Squadrons start full" exists. Presets buy from the budget instead. | M4 |
| 4 | **Turn 0.** Ground forces are bought. You spend pre-war reconnaissance, the first intel round runs, you make the opening choices, red prepares, and blue's opening missile strikes are planned. | Partly. Ground purchases and a pre-war intel picture exist. The rest doesn't. | M4 |
| 5 | **Turn 1 opens** with a BDA report on the missile strikes, and the damage is on the map. | Missing | M4 |
| 6 | **The commander plans 6 hours:** routine lines all period, strike waves, and a main push as long as the mission duration. | Exists (M1, 2026-11-10). | M1 |
| 7 | **You get a flight** from the plan, by your preferred squadron or mission type. You can pick another, or plan your own package. | Missing. Planning by hand exists. | M2 |
| 8 | **Fly.** The mission starts at your startup. Everything earlier is already fought: flights in the air are where they would be, and earlier strikers are heading home. | Partly. The fighting before the mission and the start stages exist. | M2 |
| 9 | **Only the flights you are likely to meet are in DCS.** The rest of the war is fought by the combat model at the same time. | Missing. Only ground units are culled. | M3 |
| 10 | **You quit.** The combat model fights what is left of the 6 hours. | Partly. Packages planned after the mission are fought in the 6 hour mode. Flights that hadn't finished when you quit are assumed to recover. | M2 |
| 11 | **Debrief:** your mission first, then the rest of the war. | Partly. "How the plan went" is split into the mission, before and after it (M1). "Elsewhere" needs M3. | M1, M3 |
| 12 | **The commander plans the next turn.** Phases move from OCA, SEAD and DEAD to strike and CAS. | Exists | |
| 13 | **The campaign ends** on the win condition Retribution has today. | Exists | |

Any turn can be skipped. The combat model then fights all of it. That exists today.

## 3. The turn

```
|----------------------------- 6 hour turn -----------------------------|

 routine lines: CAP, AWACS, tankers, ground alert, with reliefs =========
 wave       wave        [  MAIN PUSH  ]        wave       wave
                         as long as the
                         mission duration

 before the mission   |  during the mission       |  after you quit
 combat model         |  DCS: the bubble          |  combat model
                      |  combat model: the rest   |
```

**The period** is always 6 hours, for both sides. The commander plans all of it:

- **routine lines** for the whole period, with reliefs: CAP stations, AWACS, tankers and
  ground alert, later FAC(A);
- **strike waves** through the period;
- **the main push:** the turn's main effort in one block, as long as "Desired mission
  duration". SEAD and DEAD lead it and the strikes follow minutes later.

**The mission** is the slice of the period around your flight:

- It starts when your flight starts up.
- You are offered flights in the main push first, so by default the mission is the busiest
  part of the turn. Pick a flight in another wave and the mission moves there.
- It has no timer. It ends when you quit.

**Start stages follow the timeline.** A flight is in the air at mission start only if it
took off before then. If its time on target has passed, it is on its way home. Flights
that take off later start on the ground at their time. You start the way you chose.

**The bubble** is every flight, of either side, that you are likely to meet. Only the
bubble is in DCS.

- Always in: your package, what you need (your tanker, AWACS, escort and SEAD), and any
  package you pinned.
- Scored in: flights whose route during the mission comes near your route, target or base,
  and red CAPs and ground alerts that cover your route.
- Flights that would fight each other go in or out together. Half a fight is never left in
  DCS.
- The budget is about 10 packages per side, as guidance, not a hard limit.
- Everything outside the bubble is fought by the combat model over the same time, and
  reported in the debrief as "elsewhere".

**What the app shows.** Your flight and the main push first. Each routine line is one row
with its reliefs folded in. Other waves are folded to a line each. The debrief gives your
mission, then elsewhere, then before and after.

## 4. Scope

**In scope:** the flow in section 2 and the roadmap in section 6.

**Not doing (decided).** Don't build or propose these:

- Radio chatter.
- Missile strikes by red, and missile salvos after turn 0 for either side. There is no
  missile stock to track.
- Bombers in campaigns without an off-map base. No virtual off-map bases.
- A separate campaign brief or operations order page. The turn briefing stays.
- Changing the plan to suit the player's preference.
- A real-time clock. The war moves only when a turn is flown or skipped.
- Changes to campaign files, the ground war or the win condition.
- The WWII doctrine in the new planner. It stays on the legacy planner.

**Shelved or parked.** These need the user's word before any work:

- F27, readiness per turn or per day. A 6 hour war four times a day makes this matter
  more, so it is worth a second look after M1.
- F10 (merging packages), F21 (background helicopters), F24 (timing randomness), F31
  (ground and sea activity in the mission), stand-off SEAD.
- Turn 0 ideas suggested on 2026-11-09 and not decided: forces that arrive over the first
  turns, a weather and light forecast for the first day, a logbook for your pilot, CAP
  stations and tracks that keep their names, limited stocks of precision weapons, special
  forces or cyber actions before H-hour, and target restrictions that lift as the phases
  advance. `TODO.md` ("Parked") has the list.

## 5. Decisions

Only the user changes a decision. A change is added here with its date and what it
replaces, and then `TODO.md` and the memory notes are brought in line.

**2026-11-09, vision review:**

1. **Every turn is a full 6 hour air war.** Routine lines run all period with reliefs,
   strike waves run through it, and the main push is in the mission. The combat model
   fights everything outside DCS. *Replaces:* "the rest of each 6 h step is fully quiet"
   and "every TOT falls inside the window" (focused turns, F9).
2. **The plan is as big as the air wing can really fly, and DCS is culled.** DCS gets the
   flights near your route and target, about 10 packages per side. *Replaces:* about 10
   packages per side as the size of the plan, and "prefer fewer, visibly active flights
   over realistic but unseen volume".
3. **Two ways to play:** the commander plans, or you plan by hand.
4. **Your preference never bends the plan.** You are offered the best matches from the
   real plan: your squadron first, then your mission type.
5. **Opening missile strikes are blue only and turn 0 only.** *Replaces* "stand-off
   missile salvos are out of scope" for blue's opening. It still holds for red.
6. **Strategic bombers only where the campaign defines an off-map base.** 10 of the 70
   campaigns do, all for blue. One of them (`black_sea`) also has one for red.
7. **Turn 0 gains** red's own turn 0 with a surprise setting, the opening choices, and
   pre-war reconnaissance. A campaign brief was offered and not chosen.
8. **The DCS checks are flown in one pass at the end,** not after each milestone.
9. **Squadrons and detachments start with their aircraft, and none are bought at
   turn 0.** *Replaces* the presets buying aircraft from the starting budget.

**Earlier decisions that still hold:**

- Turns advance 6 hours, so day and night cycle.
- The mission doesn't end on a timer. AI flights finish, return and land on their own.
- AI flights start at a mix of stages, not all in the air.
- Package counts are guidance, never hard limits.
- Flights seen returning are real sorties with real airframes, and their losses count.
- Turnaround activity is shown at the player's base only (F19).
- No radio chatter (F20). F27 is shelved.
- Each side plans only from its own intel picture. Nobody reads ground truth.
- Feature branches stay separate and are merged into `Resolution`.

## 6. Roadmap

**Current milestone: M2.** M1 closed 2026-11-10 (W1–W8; W7's bands are recorded in
`TODO.md`). One milestone at a time. The game stays playable after each one. The items are
in `TODO.md` under the same names.

### M1. The 6 hour war (app only)

Every turn plans and fights 6 hours for both sides, with the main effort in a main push,
and the app is as easy to read as a focused turn is today.

- **Items:** W1 one turn model, W2 the main push, W3 red plans the same way, W4 fold the
  plan in the list and on the map, W5 briefing, W6 debrief by part of the turn, W7 bands
  in the new model, W8 saves.
- **Reuses:** 6 hour planning with reliefs and second sorties, the fighting before and
  after the mission window (`game/sim/atoperiod.py`), the grouped ATO list and the
  timeline.
- **Done when:**
  - turn 1 of a new campaign plans 6 hours for both sides, with at least one wave before
    the main push;
  - about half of the offensive times on target fall in the main push (a first value);
  - the ATO list's first view fits one screen, with the rest one click away;
  - the four test scenarios run 8 turns and their results are recorded.
- **Not in M1:** culling, assigning the player.

### M2. Your seat

You state a preference, get a flight from the real plan, and the mission is the slice
around it, before and after included.

- **Items:** P1 preference, P2 ranked offers, P3 "Your flight" card and switching, P4 the
  mission follows your flight, P5 earlier strikers heading home, P6 the fight goes on
  after you quit, P7 planning by hand.
- **Reuses:** player pilot assignment, the turn briefing, `advance_to_window`,
  `resolve_remainder`.
- **Done when:**
  - turn 1 shows a fragged flight that matches the preference when the plan has one, and a
    reason line when it doesn't;
  - picking another flight moves the mission start;
  - after quitting 20 minutes in, the debrief gives later packages results from the combat
    model instead of "not flown".
- **Needs:** the mission time in the state DCS exports (it isn't exported today).

### M3. The bubble

DCS holds only what you are likely to meet. The rest of the war is fought at the same
time.

- **Items:** B1 relevance, B2 clusters, B3 budget, B4 generate the bubble only, B5 fight
  the rest, B6 show it, B7 measure the distortion without DCS, B8 your base is alive.
- **Reuses:** ground unit culling zones, the handling of held-back packages, each side's
  radar picture.
- **Done when:**
  - a mission holds about 10 packages per side plus what you need;
  - your tanker, AWACS and escort are always there;
  - B7 shows that fighting the bubble and the rest apart gives nearly the same losses and
    target results as fighting the turn as one. The tolerance is set from the first
    measurements.
- **The risk here** is a fight split across the edge of the bubble. B2 and B7 exist for
  that reason. B7 matters more because nothing is flown in DCS until M6.

### M4. Campaign start

A new campaign starts the way a real operation would: a deployed air wing, a prepared
enemy, an opening salvo and a BDA.

- **Items:** T1 one branch with everything, T2 start with aircraft, T3 bomber detachments,
  T4 presets from real deployments, T5 pre-war reconnaissance, T6 first intel round, T7
  opening choices, T8 red's turn 0, T9 opening missile strikes, T10 turn 1 BDA.
- **Reuses:** the preset placer, off-map bases, SAM moves with emission control and
  decoys, the intel picture with uncertain BDA, the commander's target list.
- **Done when:**
  - a campaign started from a preset shows no aircraft purchase at turn 0 for either side;
  - bombers appear only where the campaign has an off-map base;
  - turn 1 opens with a BDA report, and it changes with the surprise setting and the
    opening emphasis.
- M4 doesn't depend on M1 to M3. It can be moved earlier if the user asks.

### M5. Realism and balance

- **Items:** V1 full test matrix, campaign pace and economy in the new model, V2 planner
  leftovers (only where a band fails or a symptom is named), V3 FAC(A) line, V4 CSAR, FARP
  and parking in the period, V5 docs and tests.

### M6. The DCS pass

All the checks in `TODO.md` ("Checks in DCS") in one pass, then the fixes, then a frame
rate and unit count measurement.

## 7. Where the work had drifted (review, 2026-11-09)

1. **The plan was shrunk to fit the mission.** Focused turns made the turn as small as the
   mission. The vision is the opposite: keep the war big and shrink what DCS shows. The
   start stages, airborne fuel, turn briefing, debrief, parking cleanup and SEAD corridors
   carry over. "The period is the mission", "every TOT inside the window", "the rest is
   quiet" and the two returning CAPs don't.
2. **Planner tuning ran ahead of the player's seat.** The latest work (TODO items 6 to 9,
   the risk fit for focused turns) changed how the two AIs fight each other. None of it
   changed what the player does. Part of that fit is specific to the mission-only model.
3. **No branch runs the whole flow.** Presets are on `airwing-presets` and `Resolution`.
   The planner is on `combat-resolution`, 27 commits and about 32,500 lines ahead of
   `Resolution`.
4. **Nothing since the OPFOR planner has been flown.** 10 DCS checks and 6 app checks are
   open. Decision 8 keeps them for the end, so every item that changes the mission needs a
   test on the generated mission.
5. **The TODO had one flat order.** Its 48 items weren't tied to a step of the flow, so
   nothing said which ones mattered most.

## 8. Staying on track

**The scope test.** Answer these before starting an item. If an answer is missing, the
item goes to "Shelved or parked" with one line, and isn't built.

1. **Flow:** which step in section 2, or which principle, does it serve?
2. **Seen:** what will the player see or feel differently, in the app or in DCS? If only
   AI-against-AI numbers change, which test band is failing?
3. **Clutter:** if it adds something to a screen, what does it fold or replace?
4. **Decided:** is it under "Not doing", or shelved?
5. **Checkable:** which test, e2e number or DCS check will show it works?

**Working rules:**

- One milestone at a time, in order. A new idea goes on the parked list, not into the
  current milestone.
- Tune planner and risk constants only when a test band fails or a symptom is named. Keep
  one tuning item open at a time, and record the numbers before and after.
- Every change to the generated mission gets a test on the generated mission and an entry
  under "Checks in DCS" in `TODO.md`.
- Merge the feature branches into `Resolution` when a milestone closes, and run the tests
  there.
- When a milestone closes, update the "Today" column in section 2 and the "Current
  milestone" line in section 6.

## 9. Assumptions to confirm

Readings of the vision that weren't asked about. Each one is how the work will go unless
the user says otherwise.

1. "The campaign continues when DCS isn't running" means any turn can be fought by the app
   alone, and the hours you don't fly are fought by the app. It doesn't mean a real-time
   clock.
2. Start stages follow the timeline (section 3). "Flights whose TOT is inside the mission
   start in flight" holds only for those that took off before the mission started.
3. The mission starts at your flight's startup. Nothing is moved in the plan to make that
   so.
4. Starting aircraft are free for both sides. Replacements later in the campaign are
   bought, as today.
5. The opening salvo's size comes from the faction and its era, and is raised by the
   cruise missile ships and bomber detachments actually in the campaign.
6. When you plan by hand, the commander still flies the routine lines unless you switch
   those off too. Red is always planned by its commander.
7. "FACs" means FAC(A) flights over active fronts, as a routine line (M5).
8. With several players, the mission starts at the earliest player startup and every
   flight with a player in it shapes the bubble. There is one preference per campaign.
9. Today's focused turn stays as an option ("Mission only") and gets no new features.

## 10. Terms

- **Turn, period:** 6 hours of war. Each commander plans one air tasking order for it.
- **Routine lines:** CAP stations, AWACS, tankers, ground alert, FAC(A). They run all
  period with reliefs.
- **Wave:** a group of strike packages with times on target minutes apart.
- **Main push:** the turn's biggest wave, as long as "Desired mission duration".
- **Mission:** what DCS flies. It starts at your startup.
- **Bubble:** the flights of both sides that are in the mission.
- **Elsewhere:** everything outside the bubble during the mission.
- **Key package:** a package with a purpose worth a line in the briefing. Routine lines
  aren't key.
- **Combat model:** the fast-forward simulation that fights whatever DCS doesn't.
