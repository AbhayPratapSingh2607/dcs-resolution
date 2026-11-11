# Fire missions

From turn 1 you can plan cruise missile, ballistic missile and artillery strikes for the
turn, and the enemy's commander plans its own. Strikes timed inside the DCS mission are
fired in DCS; the rest are fired by the combat model at their time, like the flights it
flies. (Turn 0's strikes are the [opening salvo](Air-Campaign-Planner.md#the-opening).)

## Launchers

Each launcher fires up to its capacity every turn. There is no stock to track.

| Launcher | Rounds per turn | Reach | Fires at |
|---|---|---|---|
| Cruise missile ship (Ticonderoga, Arleigh Burke) | 8 Tomahawks a ship | 1000 km | fixed sites and airfields |
| Missile site (Scud) | 1 a launcher | 300 km | fixed sites and airfields |
| Missile site (V-1) | 1 a ramp | 250 km | fixed sites and airfields |
| Front-line artillery | 10 rounds a gun | its range less how far behind the front it stands | sites near the front |

Artillery stands where the front line generator puts it: 16–18 km back when its range allows
(an MLRS reaches about 15 km past the front), otherwise with the tanks about 3 km back.
Missiles aren't fired at mobile SAMs or ships, and you can only aim at what your intelligence
knows of.

## Planning

**Fire Missions** in the top bar (from turn 1) lists this turn's strikes: time, launcher,
rounds, target and what happened. **Plan fire mission…** on an enemy site's window plans one at
that site.

* **Add…** picks a launcher (with what it has left this turn), a target in its reach
  (nearest first, with its type and distance), the rounds and the time. The time starts
  10 minutes into the DCS window, and the window tells you whether the strike is inside
  the mission or not.
* **Suggest** lets the commander fill what the launchers have left: the highest value targets
  in reach (command posts, radars, long-range SAMs, airfields first), spread over the turn,
  two to four missiles a target, four at an airfield.
* **Remove** takes a strike out, unless it has already been fired.

## On the map

Every target of one of your strikes has a red ring around it, and its tooltip lists the
strikes: time, rounds, weapon and launcher ("Fire mission 21:10: 4 Tomahawk from AARDWOLF",
"Fired …" once it has gone). On turn 0 the rings mark the opening salvo's targets instead
("Opening salvo: 3 cruise missiles"), as planned with the current emphasis; they're gone if
the opening missile strikes are turned off. Red's strikes aren't shown.

## How they are fired

* **In DCS.** A strike timed inside the DCS window gives its launcher a fire task at that
  time: ships fire Tomahawks, Scud sites their missile, and the side's artillery groups at
  that front share the rounds. A launcher with a strike in the window is kept in the
  mission even when culling would drop it. The damage comes back with the mission's results.
  If you quit DCS before a strike's time, the combat model fires it.
* **By the combat model.** Everything else: strikes before the window are fired while the
  turn is fought up to it, those after it at the end of the turn, and all of them when the
  whole turn is fast-forwarded. Each Tomahawk hits with 80% (less inside the defender's SAM
  cover), a Scud with 30%, and each artillery round kills about 0.05 units. Hits kill radars
  first; two hits on an airfield cut its runway, and some hit aircraft parked in the open.
* A strike whose launcher was destroyed, or whose target is gone, is cancelled.

At the end of the turn a message lists what your strikes did.

## The enemy

Red's commander plans its strikes each turn with the launchers it has, at the highest value
targets it knows of in reach. On turn 1 its counter-strike follows the strategic surprise: all
its launchers with no surprise, half with partial surprise, none with full surprise. You don't
see red's planned strikes.

## Settings

**Fire missions (missile and artillery strikes)**, Campaign Doctrine → Intelligence, morale and
electronic warfare. Off: no fire missions for either side.
