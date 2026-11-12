# Intelligence, fog of war and morale

In Retribution, both sides know where everything is, and the map shows it all. In Resolution,
each side only knows what it has found. The commanders plan from their own side's picture, the
map shows you blue's picture, and the combat model gives unknown sites the surprise they
deserve.

This page covers the war layer around the fighting: what each side knows, how it finds out, how
it is fooled, and how losses wear it down.

## The intelligence picture

Each side keeps a picture of the enemy's ground objects: which ones it knows about, how
confident it is, roughly where they are, and which of their units it believes destroyed.

**Sources**, roughly from worst to best:

1. the pre-war picture;
2. early warning radars and AWACS listening for emitters (ELINT);
3. pilots seeing things on the way to their targets;
4. sites revealing themselves by firing;
5. strike crews reporting what they hit;
6. dedicated reconnaissance (the **Recon** mission type);
7. satellites and intelligence agencies (below).

**What it means in play:**

* **The commanders only plan against what they know.** A SAM site nobody has found doesn't
  appear in the target list or the risk estimate. It gets the first shot.
* **Battle damage assessment can be wrong.** Crews over-claim, and a target assessed below its
  desired effect is struck again.
* **Intelligence goes stale.** Mobile targets drop off the target list once their intel is two
  turns old. A mobile SAM that moved is still believed to be at its old position until it is
  found again.
* **Phantom threats.** False reports look like any other contact. The planner routes around
  them until imagery or reconnaissance clears them.

## Fog of war on the map

**Fog of war on the map** sets what you see of enemy forces:

| Setting | What the map shows |
|---|---|
| **Strict** (default) | Undetected sites are hidden. Detected ones are shown at their estimated position, with an uncertainty ring until confirmed. |
| **Soft** | Everything, with unconfirmed sites marked. |
| **Off** | Everything, as in Retribution. |

Hover an enemy site to see how you know about it, for example "Detected via satellite imagery,
turn 2, confidence 72%". Ships at sea and airbase facilities are always visible.

With fog of war on, the enemy's ATO, its view in the ATO timeline and its air campaign page are
hidden. You know the enemy's air operations only from the flights your radars see.

**The Intelligence window** has two Resolution pages:

* **Intel picture:** national resolve, front-line morale, your intelligence capability, and
  every enemy site you know about with how you know it.
* **Air campaign:** the commander's phase, intent and measures of effectiveness, the
  apportionment, the target list with BDA, the ground alert, and why packages were scrubbed.

## Satellites and agencies

**Imaging satellites.** Nations with a space programme get a number of imaging passes each turn.
They are tasked automatically on the areas that matter most: the fronts, sites known only
vaguely, enemy airbases, and places nobody has looked at yet.

* Optical satellites see best, but need daylight and clear skies. Under overcast or at night a
  pass is wasted.
* Radar (SAR) satellites see through weather and darkness, but identify less.
* Each pass covers one swath about 100 km across, so a side can only look at a few places a
  turn.
* Imagery is old by the time it is analysed. Mobile units may have moved, so their positions
  carry extra error.
* Camouflage hides mobile units, and decoys fool imagery easily.

**Intelligence agencies** produce a few products each turn:

* **Order of battle:** estimates of aircraft and armor at enemy bases improve.
* **Site tips:** agents report enemy sites. Many are vague, some point at decoys, and some are
  simply wrong.
* **Warnings:** signals intelligence reads enemy preparations. An expected offensive makes the
  AI dig in, and you get reports saying how sure the agency is. Warnings can be false alarms,
  and real offensives can be missed.
* **Battle damage:** agencies confirm or contradict strike reports.

An agency's reliability is its capability, reduced by the enemy's counter-intelligence.
Everything it produces is uncertain. Both sides get satellites and agencies by the same rules,
set by their doctrine.

## Deception

Forces with a deception doctrine set up decoys next to their mobile air defenses and vehicle
groups: inflatable launchers, dummy radars, and burnt-out wrecks dressed as live vehicles. Soviet
maskirovka and Serbian practice in 1999 are the models.

* Imagery and agents are easily fooled. ELINT much less so, since most decoys don't radiate.
* A side whose picture of a site has latched onto a decoy believes the decoy's position with
  high confidence. Strikes against it hit the decoy, the crews report the site destroyed, and
  the real site lives to fight.
* **The decoy call.** A package sent against a site its side holds as a decoy gets one roll,
  before the mission is flown, to see through it:
  * the chance is 15%, plus 35% of the side's ISR;
  * a SEAD element in the package adds 20%;
  * it falls off with the real site's distance from the decoy, to nothing beyond 20 km;
  * it is at most 85%.

  A package that sees through the decoy attacks the real site, and one that doesn't bombs the
  decoy. DCS and the combat model follow the same call. In DCS the decoys are inert vehicle
  groups of the site's own types, with radars off and weapons held, and the AI's attack tasks
  point at the decoy group. The debrief says which happened.
* Every flight's target marks sit where its side believes the target is, not on the real site.

## IADS health

A SAM battery fights best when it is cued by early warning radars through a working command and
control chain, and has power. Strip those away and it has to find targets with its own radar,
react on its own and run on generators. Desert Storm's opening night went for exactly these
nodes first, and so does the Western commander's Phase I.

Retribution's advanced IADS mode models command centres, comms and power. In basic mode a site
counts as networked when a friendly early warning radar covers it. The autonomous behaviour of
cut-off sites reaches Skynet in DCS too.

## Morale

Morale runs from 0 to 1. It drifts back toward a resting value set by doctrine and by the
nation's resolve. Losses and failures knock it down, and success lifts it.

* **Squadrons** fly a little better or worse, abort earlier when shaken, and stand aircraft down
  when morale collapses.
* **Ground forces** fire less and break sooner. A collapsing front may surrender units without a
  fight, and is forced to retreat.
* **SAM crews** that watched neighbouring sites die, or were hunted by ARMs, keep their radars
  dark and fire wildly.

**National war-weariness.** Sustained losses, relative to the size of a side's forces, lower its
resolve. Resolve lowers income and every morale baseline. It never ends the war by itself.

## Rules of engagement and collateral damage

Targets in or next to built-up areas risk civilian casualties when weapons go astray, or are
inherently imprecise (dumb bombs, cluster munitions, rockets).

* Each incident costs the striking side national resolve, more for nations whose public is
  sensitive to it, and hands the enemy a propaganda boost.
* Under **restrictive** rules of engagement the AI won't plan strikes against high-risk targets,
  and pilots release unguided weapons more carefully near towns.
* Built-up areas come from the theater's terrain grid (ESA WorldCover, the same grid
  [Dynamic FARPs](Dynamic-FARPs.md) use). Theaters without one use a rule of thumb by target
  type and distance to towns.

## Settings

Settings > Campaign Doctrine > Intelligence, morale and electronic warfare:

| Setting | What it does | Default |
|---|---|---|
| Intelligence: sides only know what they have detected | The intelligence picture. Off: both sides know everything, as in Retribution. | On |
| Fog of war on the map | Strict, Soft or Off (above). Requires intelligence. | Strict |
| Satellites and intelligence agencies | Imaging satellites by national capability, and agency products. | On |
| Strategic intelligence strength | Scales satellite image quality and agency reliability for both sides. | 1.0 |
| Deception: decoy sites and camouflage | Decoys beside mobile air defenses for doctrines that use them. | On |
| Morale: squadrons, ground forces and SAM crews | Morale and its effects. | On |
| National war-weariness | Resolve falls with sustained losses. | On |
| Rules of engagement | Doctrine, Permissive or Restrictive. | Doctrine |
| Collateral damage | Civilian casualties cost resolve. | On |

Changing the fog of war or intelligence setting refreshes the map at once.
