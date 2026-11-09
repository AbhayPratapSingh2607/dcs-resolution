"""What a side believes about the enemy, for planning.

The planner must never read the enemy's true state. This module answers the
questions the planner asks about the enemy through the side's intelligence
picture:

- Is a SAM site's radar still working? Only the units the side has seen die
  count as dead.
- How many aircraft does each enemy squadron have? Airbases and squadron
  locations are known from the pre-war order of battle. Counts are estimates
  whose spread depends on the side's ISR and on imagery of that base, and
  they are stable within a turn.
- How many aircraft are parked at an enemy base?

Without intelligence (the warfare layer is off) the true values are used, as
before.
"""

from __future__ import annotations

from typing import Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.squadrons import Squadron
    from game.theater import ControlPoint
    from game.theater.player import Player
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.warfare.intel import IntelPicture


def picture_for(game: Game, player: Player) -> Optional[IntelPicture]:
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return None
    return war_state.picture(game, player)


def believed_radar_reach_m(game: Game, player: Player, tgo: TheaterGroundObject) -> float:
    """Range of the site's radar SAMs the side believes still work (a TELAR,
    or a launcher with its tracking radar), meters; 0 if none."""
    picture = picture_for(game, player)
    if picture is None:
        return max(
            (g.max_threat_range(radar_only=True).meters for g in tgo.groups),
            default=0.0,
        )
    contact = picture.contact(tgo)
    dead: set[int] = contact.believed_dead if contact is not None else set()
    return max((_group_radar_reach(group, dead) for group in tgo.groups), default=0.0)


def believed_live_radar_sam(game: Game, player: Player, tgo: TheaterGroundObject) -> bool:
    """Whether the side believes the site still has a working radar SAM."""
    return believed_radar_reach_m(game, player, tgo) > 0


def _group_radar_reach(group: object, believed_dead: set[int]) -> float:
    """TheaterGroup.max_threat_range(radar_only=True), counting the units the
    side believes dead as dead instead of the truly dead ones."""
    from dcs.unittype import VehicleType

    from game.data.radar_db import LAUNCHER_TRACKER_PAIRS, TELARS, TRACK_RADARS

    trackers = set()
    launchers = []
    reach = 0.0
    for unit in getattr(group, "units", []):
        if unit.id in believed_dead or not unit.is_anti_air:
            continue
        if unit.type in TRACK_RADARS:
            trackers.add(unit.type)
        elif unit.type in TELARS:
            reach = max(reach, unit.threat_range.meters)
        elif issubclass(unit.type, VehicleType) and unit.type in LAUNCHER_TRACKER_PAIRS:
            launchers.append(unit)
    for unit in launchers:
        if any(tr in trackers for tr in LAUNCHER_TRACKER_PAIRS[unit.type]):
            reach = max(reach, unit.threat_range.meters)
    return reach


def estimated_aircraft(game: Game, player: Player, squadron: Squadron) -> int:
    """The side's estimate of an enemy squadron's aircraft."""
    true_count = squadron.owned_aircraft
    picture = picture_for(game, player)
    if picture is None or true_count <= 0:
        return true_count
    from game.warfare.intel import estimate_count

    rng = game.war_state.rng(game, f"jfacc:oob:{player}:{squadron.location.id}:{squadron.name}")
    return estimate_count(true_count, picture.estimate_quality(squadron.location.id), rng)


def enemy_squadrons(game: Game, player: Player) -> Iterator[tuple[Squadron, int]]:
    """Enemy squadrons with the side's estimate of their aircraft."""
    enemy = game.coalition_for(player).opponent
    for squadron in enemy.air_wing.iter_squadrons():
        count = estimated_aircraft(game, player, squadron)
        if count > 0:
            yield squadron, count


def estimated_parked(game: Game, player: Player, base: ControlPoint) -> int:
    """Aircraft the side believes are parked at an enemy base."""
    from game.theater.controlpoint import ParkingType

    true_count = base.allocated_aircraft(ParkingType(True, True, True)).total_present
    picture = picture_for(game, player)
    if picture is None or true_count <= 0:
        return true_count
    from game.warfare.intel import estimate_count

    rng = game.war_state.rng(game, f"jfacc:parked:{player}:{base.id}")
    return estimate_count(true_count, picture.estimate_quality(base.id), rng)
