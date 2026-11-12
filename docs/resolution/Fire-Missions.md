# Fire missions

Retribution's missile sites and artillery only fire when DCS AI decides to. In Resolution, both
sides plan **cruise missile, ballistic missile and artillery strikes** every turn, as part of
the six hour war.

* Strikes timed inside the DCS mission are fired in DCS by the launcher itself.
* The rest are fired by the [combat model](Combat-Model.md) at their time, like the flights it
  flies.

Turn 0's strikes are the [opening salvo](Playing-a-Turn.md#the-opening). Fire missions start on
turn 1.

## Launchers

| Launcher | Rounds per turn | Magazine for the campaign | Reach | Fires at |
|---|---|---|---|---|
| Ticonderoga cruiser | 8 Tomahawks | 26 | 1000 km | fixed sites, airfields, located mobile sites |
| Arleigh Burke destroyer | 8 Tomahawks | 24 | 1000 km | fixed sites, airfields, located mobile sites |
| Scud launcher | 1 | 4 | 300 km | fixed sites, airfields, located mobile sites |
| V-1 ramp | 1 | 6 | 250 km | fixed sites, airfields, located mobile sites |
| Front-line artillery | 10 rounds a gun | not counted | its range, less how far behind the front it stands | sites near the front |

* **Magazines.** With **Limited missile stocks** on (the default), each ship and missile site
  has a magazine for the whole campaign, with no reloads. The opening salvo draws on the ships'
  magazines too. With it off, each launcher fires its per-turn rate every turn.
* **Artillery** stands where the front line generator puts it: 16–18 km back when its range
  allows (an MLRS reaches about 15 km past the front), otherwise with the tanks about 3 km back.
* **Mobile sites** can be targeted once your intelligence has located them, at half the hit
  chance, because they may have moved since. The commanders keep their missiles for fixed
  targets.
* You can only aim at what your [intelligence](Intelligence.md) knows of.

## Planning

There are three ways to plan a strike:

* **Right-click an enemy site or airfield on the map.** The package dialog opens with
  **Plan Fire Mission…**. It names the best launcher in reach and its odds, or says why no
  launcher can reach the target.
* **Fire Missions** in the top bar lists this turn's strikes: time, launcher, rounds, target and
  what happened.
  * **Add…** picks a launcher (with what it has left this turn and in its magazine), a target in
    its reach (nearest first, with its type and distance), the rounds and the time. The time
    shows as +H:MM from the DCS mission start, and the dialog says whether the strike falls
    inside the mission.
  * **Suggest** lets the commander fill what the launchers have left. It picks the highest value
    targets in reach (command posts, radars, long-range SAMs and airfields first), spread over
    the turn, with two to four missiles a target and four at an airfield.
  * **Remove** takes a strike out, unless it has already been fired.
* **Your commander plans them for you.** With **Commander plans your fire missions** on (the
  default), each turn your commander plans strikes with the ATO at the highest value fixed
  targets in reach, using half of each launcher's capacity. You can move or remove them, and the
  ones you planned yourself are kept.

**On the ATO timeline,** fire missions have their own section, with one lane per launcher and
each strike drawn from launch to impact. Drag a strike to change its time. Strikes that would
overlap stack in rows.

## On the map

Every target of one of your strikes has a red crosshair, and its tooltip lists the strikes:
time, rounds, weapon and launcher. For example "Fire mission 21:10: 4 Tomahawk from AARDWOLF",
or "Fired …" once it has gone. On turn 0 the marks show the opening salvo's targets instead.
Red's strikes aren't shown.

## How they are fired

* **In DCS.** A strike timed inside the DCS window gives its launcher a fire task at that time.
  Ships fire Tomahawks, Scud sites their missile, and the side's artillery groups at that front
  share the rounds. A launcher with a strike in the window is kept in the mission even when
  culling would drop it. The damage comes back with the mission's results. If you quit DCS
  before a strike's time, the combat model fires it.
* **By the combat model.** Everything else:
  * strikes before the window are fired while the turn is fought up to it;
  * those after it are fired at the end of the turn;
  * all of them when the whole turn is fast-forwarded.

  Each Tomahawk hits 80% of the time (less inside the defender's SAM cover), a Scud 30%, and
  each artillery round kills about 0.05 units. Hits kill radars first. Two hits on an airfield
  cut its runway, and some hit aircraft parked in the open.
* A strike whose launcher was destroyed, or whose target is gone, is cancelled.

At the end of the turn a message lists what your strikes did.

## The enemy

Red's commander plans its strikes each turn with the launchers it has, at the highest value
targets it knows of in reach. On turn 1 its counter-strike follows the strategic surprise:

* with no surprise, all its launchers fire back;
* with partial surprise, half of them do;
* with full surprise, none do.

You don't see red's planned strikes.

## Settings

Settings > Campaign Doctrine > Intelligence, morale and electronic warfare:

| Setting | What it does | Default |
|---|---|---|
| Fire missions (missile and artillery strikes) | Off: no fire missions for either side. | On |
| Commander plans your fire missions | Your commander plans strikes with the ATO, using half of each launcher's capacity. | On |
| Limited missile stocks | Ships and missile sites have a magazine for the campaign. Off: each launcher fires its per-turn rate every turn. | On |
| Opening missile strikes | Blue's turn 0 salvo. | On |
