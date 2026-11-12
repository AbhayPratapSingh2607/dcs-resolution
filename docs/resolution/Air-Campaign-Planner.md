# The commanders: doctrine-driven air campaign planning

Retribution's auto planner works through a priority list of tasks until the mission is full. In
Resolution each side has a **commander** that plans the way its air force would: a Western
Joint Force Air Component Commander (JFACC), a Russian or Soviet air operation, a client state's
air defense, or an irregular force's handful of aircraft. It works from the top down:

1. assess the campaign,
2. pick a campaign phase,
3. build a prioritized target list,
4. split the sorties between mission types,
5. build packages sized to the threat,
6. lay them out on a deconflicted six hour timeline: routine lines, strike waves and a main push.

How you fit into that plan is in [Playing a turn](Playing-a-Turn.md). This page is about how the
commander makes it.

**Both commanders are real.** Blue and red each plan by their own doctrine, from their own
intelligence. A commander never sees ground truth. Enemy aircraft numbers are estimates, SAM
sites it believes destroyed are planned around as destroyed, and enemy flights it never saw
teach it nothing (see [Intelligence](Intelligence.md)).

Every doctrine except WWII uses a commander by default, each with its own planning profile (see
[Doctrines](#doctrines)). WWII factions keep the legacy planner. Both can be changed per side.

## Turning it on

Settings > Campaign Management > HQ Automation:

| Setting | What it does |
|---|---|
| Air campaign planner (OWNFOR / OPFOR) | **By faction doctrine** (the default), **Doctrine-driven air campaign (JFACC)**, or **Legacy priority planner** (Retribution's). |
| Acceptable attrition per sortie override | Replaces the doctrine's loss limits (see [Risk](#risk-and-scrubbing)). 0 keeps the doctrine's limits. |
| Automatic package planning behavior | **No preference**: the commander plans everything and frags you a flight. **Commander flies routine lines, you plan the rest**: CAP, AWACS, tankers and alerts are planned for you, and the strikes are yours. |

The turn model settings (the six hour turn, the bubble, Mission only) are in
[Playing a turn](Playing-a-Turn.md#settings).

Which planning profile a doctrine uses is set by `planning_profile:` in
`resources/combat/doctrines.yaml`. The profiles, with every number on this page, are in
`resources/doctrine/planning/`. A profile can `extends:` another and change only what differs.

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
  * **Tanker tracks follow the receivers.** A boom can't refuel a probe, and a drogue can't
    refuel a receptacle. So there is a boom line off the front base for land-based boom
    receivers (F-15, F-16, A-10, bombers), flown only by boom tankers. Each carrier or LHA with
    probe squadrons aboard gets a drogue line between it and the enemy's air defenses. Land-based
    probe aircraft get a drogue line 20 NM behind the boom track. The tracks with the most
    receivers come first, up to `enablers.tanker_tracks_max` (3). A system with no tanker of its
    own in the air wing gets no line. Which aircraft use which system is in
    `resources/combat/fuel.yaml`.
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
* **The decoy call.** A package sent against a site its side holds as a decoy gets one roll,
  before the mission is flown, to see through it: 15% plus 35% of the side's ISR, plus 20% with
  a SEAD element in the package, less the farther the real site (none beyond 20 km), at most
  85%. Seen through, the package attacks the real site; otherwise it bombs the decoy, and the
  crews may report the site destroyed. DCS and the combat model follow the same call; in DCS the
  decoys are inert vehicle groups of the site's types (radars off, weapons held), and the AI's
  attack tasks point at the decoy group. The target marks of every flight sit where
  its side believes the target is.

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
(`enemy_fighter_availability`) describes a 6 hour ATO. In a [Mission only](Playing-a-Turn.md#mission-only)
turn both air forces fly the turn's sorties within the mission window, so the share is scaled by
6 hours over the window, up to 1.

The **Air campaign** page of the Intelligence window shows:

* the phase, the commander's intent and the MOEs,
* the apportioned and planned sorties,
* the JIPTL with BDA,
* the QRA ground alert,
* why packages were scrubbed.

Each package's dialog shows the reason it was planned and its estimated attrition.

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
