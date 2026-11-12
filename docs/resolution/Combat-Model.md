# The combat model

In Retribution, fast forward either pauses at the first contact or settles combat with a few
dice rolls. In Resolution, fast forward **fights it out**. Most of each six hour turn is fought
this way: everything before your mission, everything outside the bubble during it, and
everything after you quit (see [Playing a turn](Playing-a-Turn.md)).

The model works from the units, weapons, sensors, pilot skill, tactics, fuel and weather
involved. It runs in 10 second rounds with seeded randomness. Losses and damage carry into the
mission and into the campaign, the same as DCS results.

It is calibrated against the historical record: Desert Storm, Allied Force, Linebacker II,
Yom Kippur and the Desert Storm air-to-air war. NATO rarely loses many aircraft against Iraq or
Iran, and a peer fight is costly for both sides.

## Turning it on

Settings > Mission Generator > Gameplay:

| Setting | What it does | Default |
|---|---|---|
| Resolve combat when fast forwarding by | **Resolve combat**: fight it out with the model. **Pause simulation**: stop fast forward at the first contact and generate the mission there (Retribution's behaviour). **Skip combat**: no combat while fast forwarding. Choose **Resolve combat** for the six hour war. | Pause simulation |
| Combat model lethality | Scales every weapon's kill probability. 1.0 is calibrated against history. | 1.0 |
| Historical force quality in the combat model | Training, readiness, air defense integration and doctrine differ by faction (see [Force quality](#force-quality)). Off: only equipment differs. | On |
| Simulate front-line battles while fast forwarding | Front lines fight during fast forward, and their losses move the front. | On |
| Front-line battle round length (minutes) | How often a front fights a round. | |

The parts of a turn the model fights after your mission (the bubble's rest and what comes
after you quit) always use **Resolve combat**.

## Air-to-air

Each engagement runs in 10 second rounds:

1. **Detection.** Each side builds a picture of the other from:
   * onboard radar, whose range scales with the target's RCS, and look-down capability against
     low targets;
   * IRST and eyeballs;
   * the off-board picture from AWACS and EWR/GCI.

   The side that sees first shoots first, and a target that hasn't seen the shooter is far more
   likely to die.
2. **Beyond visual range.** Committed fighters pick targets by role: escorts protect their
   package, and CAP goes for the strikers. They fire when the target is inside the range their
   skill and the geometry allow. Missiles fly for real time, and semi-active radar missiles
   need their shooter alive and supporting until impact.
3. **Defense.** Targets aware of the shot (RWR, missile warning, eyes) defend with chaff,
   flares, notching, jamming, and their own skill and agility. A defending aircraft can't press
   its own attack.
4. **The merge.** Inside visual range the fight becomes a series of close-in duels, decided by
   agility, skill, high off-boresight missiles, numbers and light.
5. **Decisions.** After each round, flights decide whether to keep fighting. CAP and escorts
   break off when out of missiles, after heavy losses, when badly outnumbered or at bingo.
   Strikers engaged without cover abort, jettison and go home, and support aircraft run.

A CAP that can't catch an enemy inside its commit range waits 5 minutes before trying again.

## Surface-to-air

A SAM site is a set of launchers, with magazines and fire channels, that depend on their
tracking radars. Each round, a site that can see the target fires salvos, the target defends,
and any SEAD in the package hunts the radar.

* **The radar horizon and altitude envelopes** matter. Flying low gets you close to a
  long-range SAM before it sees you. Flying high keeps you out of MANPADS and AAA.
* **Kill probability is a combat chain, not a test-range figure.** It includes readiness, crew
  proficiency, missile reliability, jamming, towed decoys and evasion.
* **Sites remember.** Missiles fired are gone, radars destroyed by anti-radiation missiles stay
  dead, and a site that went dark to dodge an ARM stays suppressed for a while.
* **The network matters.** A battery cued by early warning radars through working command and
  control, with power, fights best. Strip those away and it fights alone on its own radar. See
  [IADS health](Intelligence.md#iads-health).
* **Emission control** orders from the enemy commander (active, ambush, dark) apply. See
  [IADS management](Air-Campaign-Planner.md#iads-management).
* **Ships.** A HARM that hits a warship wrecks its radars and silences its SAMs for six hours;
  it doesn't sink it. Boats armed only with guns and MANPADS aren't hunted by HARMs.

## Air-to-ground

When a flight reaches its IP, the model flies the attack:

* The flight descends, or doesn't, to its release altitude. It runs the gauntlet of point
  defenses around the target unless its weapons outrange them.
* It delivers what it is **actually carrying**, from its real loadout.
* **Hits depend on guidance:**
  * lasers need a designator and a clear line through the clouds;
  * TV seekers need daylight;
  * GPS doesn't care about weather, but can't hit moving targets;
  * dumb bombs need a skilled pilot and good visibility.
* **Kills depend on the warhead** against what was hit. Rockets don't drop hardened shelters,
  and 2000 lb bombs do.
* **CAS** makes 4 attack passes per aircraft and sortie over the front, with its most effective
  weapons first, and brings the rest home. A FAC(A) overhead makes visual, rocket and laser
  attacks hit more often.
* **Decoys.** A package that takes a decoy for the target bombs the decoy (see
  [Deception](Intelligence.md#deception)).

## The front lines

Each front fights a round every few simulated minutes, about 10 rounds a turn, using the combat
groups the ground planner deployed. Losses follow a modified Lanchester square law. Each side's
killing power grows with how many weapons it brings and what they are good against.

* **Stance** decides who is attacking. Attackers are exposed in the open, and defenders in
  prepared positions take far fewer losses (the classic 3:1 rule falls out of this). Dug-in
  anti-tank missiles hit harder.
* **Breakpoints.** An attack breaks off at 25% losses and a defense at 35%. A broken or
  retreating side barely shoots back, and the round drops to pursuit.
* **Artillery** fires from behind the line at everything, and only counter-battery fire
  touches it.
* **Air support** lands on the same combat groups, so a front with air superiority grinds the
  enemy down.
* **Night and weather** blunt direct fire, unless the unit has thermal sights.
* **Morale** changes how hard units fight. A collapsing front may surrender units without a
  fight (see [Morale](Intelligence.md#morale)).
* **Base capture.** A base falls in a fast-forwarded turn when its front strength is spent, it
  has no armor left, and the side attacking across that front still has at least 4 ground units
  on an aggressive, elimination or breakthrough stance. DCS missions still capture bases only
  through their triggers.

## Weather and light

Weather degrades specific capabilities, not combat as a whole:

* Radar and GPS weapons ignore clouds. Laser designation and TV seekers don't.
* Night hurts eyeballs, but not radars.
* At night the commanders send only aircraft with sensors on attack missions.

## Fuel and tankers

Each flight gets a fuel margin: how much fuel it has left to fight, loiter and re-attack once it
reaches its target. A short hop leaves plenty. A mission flown near the edge of the aircraft's
combat radius leaves almost nothing.

* **Tankers.** A friendly tanker in reach tops the flight up: one planned into the package, or
  a theater tanker on its orbit within 450 km. It has to be a tanker of the right system, boom
  or drogue, and it only helps aircraft that can refuel in the air. A tanker that is shot down
  stops supporting its flights at once.
* **Air-to-air:** fighters short of fuel reach bingo sooner, and fighters with a tanker behind
  them later.
* **Strikes:** below a margin of 0.35 the attack is rushed, and below 0.1 the flight may abort.

## Aircrew

Every loss records where the aircraft went down and what got it. CSAR uses that instead of a
flat survival roll and a spot near the package's target. A pilot downed by an SA-10 on the way
in comes down on the way in. The chance of ejecting depends on the kind of hit:

* proximity-fused missiles at altitude leave time to eject;
* guns and flak at low level often don't;
* helicopter crews ride the aircraft down.

The factors scale **CSAR pilot survival chance**. Historically about half the aircrew shot down
survived (Vietnam, Desert Storm). See [CSAR](CSAR.md).

## Force quality

Equipment is only part of the story. In modern air campaigns, training, readiness, integration
and doctrine mattered as much. Iraqi and Syrian SAM crews fired hundreds of missiles for a
handful of kills, and Serbian crews survived 78 days by barely radiating and hit almost
nothing.

Each faction is matched to a tier by its name: `nato_tier1`, `western`, `peer`,
`soviet_coldwar`, `client_state` or `irregular`. Each tier scales:

* aircrew skill;
* SAM crew proficiency;
* readiness (the share of launches where the missile and ground equipment work);
* IADS integration;
* fear of anti-radiation missiles;
* stand-off doctrine;
* dependence on ground control;
* self-protection jamming.

The skill settings still apply on top as a difficulty adjustment. The data and its historical
rationale are in `resources/combat/force_quality.yaml`.

## The after-action report

After a turn fought by the model, the debriefing has an after-action report for each side:

* aircraft lost, by cause and by type;
* what happened to their crews: killed, waiting for rescue, captured or recovered;
* front-line vehicles lost at each front;
* other losses: site units, convoys, cargo ships and runways;
* what the side achieved: air kills, successful strikes, aborts and bingo break-offs;
* where its intelligence came from.

**Key events** follow: front lines that broke or attacks that culminated, tankers lost, flights
short of fuel, strikes that found nothing left, and decoys.

The mission results window shows the full combat log as it happened, with every shot, hit, miss
and break-off and its time.

## The data

Everything is data in `resources/combat/*.yaml`: aircraft, weapons, air defenses, ground units,
force quality, fuel and doctrines. Anything without an entry is derived from what Retribution
already knows (year of introduction, unit class, pydcs ranges, task priorities, weapon names).
That way modded units still take part sensibly.

## Checking it without DCS

| Tool | What it does |
|---|---|
| `resources/tools/combat_calibration.py 100` | Runs the calibration scenarios 100 times each and checks them against their bands, including the historical validation (Desert Storm, Allied Force, Linebacker II, Yom Kippur). |
| `resources/tools/campaign_e2e.py --turns N` | Plays a campaign headless. Each turn it fast-forwards, commits the results the way the app does, prints the after-action report and checks invariants. |
| `resources/tools/campaign_matrix.py` | Plays scenarios over several seeds and checks them against historical bands (see [Checking the commanders](Air-Campaign-Planner.md#checking-it-without-dcs)). |
| `resources/tools/bubble_distortion.py SAVE --seeds 5` | Fights a saved turn's window whole, and split into the bubble and the rest, and compares the losses. |

```
.venv/Scripts/python resources/tools/combat_calibration.py 100
.venv/Scripts/python resources/tools/campaign_e2e.py --turns 4 --seed 3
```
