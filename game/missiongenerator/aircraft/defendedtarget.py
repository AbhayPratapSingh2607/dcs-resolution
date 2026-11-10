"""Detects attack missions whose target is covered by enemy air defenses.

AI ground attack flights left to their own devices will press home gun runs and low
rocket passes until the target is dead or they are out of bullets. Against an
undefended convoy that's fine, but against a target sitting under SAMs or AAA it gets
them killed. Mission generation uses this check to restrict those flights to their
primary munitions so they make their attack and leave.

Helicopters are left alone: their guns are standoff weapons, not a reason to dive
through the target area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.data.units import ANTI_AIR_UNIT_CLASSES
from game.theater import ControlPoint, FrontLine, TheaterGroundObject
from game.utils import nautical_miles

if TYPE_CHECKING:
    from game.ato import Flight

# Added to each air defense's engagement range. Gun runs and rocket passes carry the
# attacker well past the target, so a site whose envelope only just misses the target
# point is still a threat to the attack run.
THREAT_MARGIN = nautical_miles(1)


def target_area_defended(flight: Flight) -> bool:
    """True if the flight's package target is within reach of enemy air defenses.

    Unlike the coalition threat zones (which ignore anything shorter ranged than 3nm
    because it isn't worth routing around), this includes short range AAA and MANPADS,
    since those are exactly what kills aircraft making gun runs.
    """
    game = flight.coalition.game
    if not game.settings.ai_avoid_gun_runs_in_defended_areas or flight.is_helo:
        return False

    target = flight.package.target
    if isinstance(target, TheaterGroundObject) and target.has_aa:
        return True

    enemy = flight.coalition.opponent.player
    if isinstance(target, FrontLine) and front_line_has_air_defense(
        target.control_point_friendly_to(enemy)
    ):
        return True

    for control_point in game.theater.control_points_for(enemy):
        for tgo in control_point.ground_objects:
            if not tgo.has_aa:
                continue
            reach = tgo.max_threat_range() + THREAT_MARGIN
            if tgo.position.distance_to_point(target.position) <= reach.meters:
                return True
    return False


def front_line_has_air_defense(control_point: ControlPoint) -> bool:
    """True if the ground forces this base sends to the front include air defense.

    Front line units are generated from the base's armor inventory rather than being
    ground objects, so they are invisible to the TGO scan above.
    """
    return any(
        count > 0 and unit_type.unit_class in ANTI_AIR_UNIT_CLASSES
        for unit_type, count in control_point.base.armor.items()
    )
