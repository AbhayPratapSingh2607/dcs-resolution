# The DCS pass (M6)

Every open "Checks in DCS" item in `TODO.md` (D1–D22), grouped into five sessions so that one
campaign covers as many as it can. The details of what to expect are in each D item; this sheet
says where and in which order to look. Tick the item in `TODO.md` once it's flown. For
problems, keep `Saved Games\DCS\Logs\dcs.log`, the state file and a Tacview recording, and
note the turn and the save.

Before every session:

* Settings → Plugins: **GCI ground alert scrambles** on (with `announce` and `debug`),
  **Skynet IADS** on, **Parking cleanup** on (with `debug`).
* Settings → Campaign doctrine: fog of war **off** for sessions 1–3, so the app shows red's ATO
  to compare with DCS (session 4 turns it on).
* Settings → Campaign management: **Mission only** off, **Automatic package planning behavior**
  "No preference", **Full turn: only what you'd meet is in DCS** on.
* Tacview recording on.

## Session 1: a new war (Caucasus, Black Sea)

Campaign `black_sea` (both sides have an off-map base and a carrier group). Blue USA 2005 with
the **USAF 2005** air wing preset, red Russia 2015 (or 2010) with the **Russian VKS 2015**
preset.

1. **Turn 0.** No aircraft are bought; squadrons show their aircraft; the B-1B and B-52H
   detachments are at the off-map base only. The amber pre-war note is above the package list
   (A2). → D16
2. **Begin Campaign.** The opening dialog: pick H-hour, emphasis "Air defenses", surprise
   "None", leave the recon areas as offered. Turn 1 starts at H-hour; the briefing opens with
   **The opening** (estimate, recon areas, BDA). → D16, A5
3. **Your flight.** The Your flight card names your flight and up to 8 offers; take another
   offer and back. → D12
4. **The plan.** The ATO list is folded, the timeline shades the main push and the DCS window,
   the map draws CAP stations and tracks as dashed circles, packages elsewhere are dimmed.
   **Bubble…** lists every package with its reason. → D11 (folding, map), D15
5. **Take off and fly.** At mission start (F10 map, Tacview):
   - only the bubble's packages, plus parked aircraft at your base; → D15
   - flights that took off earlier on their routes, flights past their TOT without bombs or
     ARMs; → D12
   - targets hit by the opening salvo show wrecks; a hit airfield has craters; red SAMs are not
     all where the app first showed them (surprise "None"); → D16, D5
   - the cold start flights on the carrier deck all have a spot; count them; → D18
   - red alert pairs launch when you are detected, and never more than 2 per raid; → D1
   - SAMs set to ambush or dark behave so; no Skynet errors; → D2
   - AI flights that land disappear about 10 minutes after shutdown; → D10
   - CAPs, AWACS and tankers set to On Station are on their tracks. → D8
6. **Quit after about 20 minutes.** The debrief's **How the plan went** has your mission,
   elsewhere during it, before and after it, with results (not "not flown") for the flights
   that hadn't finished. → D13, D15, A6

## Session 2: ground war and FAC(A)

Same campaign, a few turns on (fast-forward turns until Phase III or IV, or until a front has
troops in contact on blue's main effort).

1. Frag yourself on a CAS package over the main effort whose rationale names a FAC(A); the
   kneeboard JTAC list has it with its frequency. In DCS, check in on that frequency: the AI
   FAC(A) should talk you on and mark; note what it actually does. → D17
2. With the behaviour "Commander flies routine lines, you plan the rest", pass a turn: only
   lines are planned; plan a strike, pin it with **Keep in my mission**. → D14
3. Place a dynamic FARP at the start of a turn, fly a mission that starts after its setup
   flight has landed: after the turn the FARP is established. → D18
4. If an AI air assault is planned outside your mission on an undefended base, the base
   changes hands after the turn. → D18
5. Keep fast-forwarding until a base falls in the fast forward, then fly the next mission: the
   base has its new owner and a new front, and the mission loads without errors. → D6

## Session 3: Russian and Soviet tactics

A campaign with a Soviet-era red (e.g. Soviet VVS 1985) in its initial air operation phase.

1. Red raids share a raid id; they arrive suppression, sweep, main group, follow-up, minutes
   apart. → D4
2. Red strikers fly ingress and egress at about 500 ft (Tacview). → D3
3. After a turn where a red mobile SAM fired, fog of war on: the map shows the old position,
   DCS the new one; decoys near the radar SAMs. → D5

## Session 4: the switches

1. **Mission only** on: pass a turn, generate the mission. Take off goes straight to the
   mission; the lead-in, the returning CAPs and the mixed start stages as in D9 and D7. Turn it
   off again: the 6 hour period comes back (A4). → D7, D9, A4
2. Pass a turn without a player flight: Take off asks fast-forward, AI-only window, or back;
   fly an AI-only window from the picker. → D11, D12
3. **Full turn: only what you'd meet is in DCS** off: every package flying in the window is in
   DCS. → D15
4. Fog of war on and off while red's ATO is shown (A1). Fast forward a turn with CAPs near an
   enemy AWACS: quick, no "0 shots" restarting (A3). → A1, A3

## Session 5: Persian Gulf, the Strait of Hormuz

The save `dcs-resolution-PG` (Super Hornets on CVN-75), Settings → Mission generator:
**Culling of distant units** on.

1. Generate the mission; it loads cleanly. Briefing: "AEW&C", packages by TOT with take-off
   times, stations one line each. One AWACS line from the carrier, relieved in turn, never two
   side by side. → D19
2. F10 map: no parked red aircraft or missile launchers at Kish, Lavan, Bandar Lengeh or
   Qeshm unless your route or a target is near; the carrier's deck and your ramp are full.
   → D20
3. Fly the anti-ship flight on the two ship group (or watch the AI one in Tacview): missiles
   go to both hulls. → D20
4. End the mission: the debriefing's plan report lists this turn's packages (yours first)
   with what was killed in DCS, and before and after the mission the combat model's part.
   → D21
5. Watch the DEAD packages (Tacview): the DEAD flight releases JSOW/JDAM on its SAM from the
   IP, it doesn't turn home with its weapons. → D22

## Afterwards

The fixes, then a frame rate and unit count measurement on a busy theater (session 1's first
mission is a good one: note the frame rate at mission start and the unit count in the F10 map
or the mission editor).
