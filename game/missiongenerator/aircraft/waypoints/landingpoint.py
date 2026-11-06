from typing import Optional

from dcs.point import MovingPoint, PointAction
from dcs.task import Land
from dcs.unit import FARP, BaseFARP

from game.theater import Airfield, ControlPoint, NavalControlPoint
from .pydcswaypointbuilder import PydcsWaypointBuilder

#: How far from a FOB's position its helipads can be.
MAX_PAD_DISTANCE = 2000


def pad_spots(pad: BaseFARP) -> int:
    """How many helicopters can park on a helipad (only the big FARP has 4)."""
    return 4 if isinstance(pad, FARP) else 1


class LandingPointBuilder(PydcsWaypointBuilder):
    def build(self) -> MovingPoint:
        waypoint = super().build()
        if self.ai_despawn(waypoint):
            waypoint.alt = round(self.flight.unit_type.preferred_patrol_altitude.meters)
            waypoint.alt_type = "BARO"
        else:
            waypoint.type = "Land"
            waypoint.action = PointAction.Landing
            if (control_point := self.waypoint.control_point) is not None:
                if isinstance(control_point, NavalControlPoint):
                    waypoint.helipad_id = control_point.airdrome_id_for_landing  # type: ignore
                    waypoint.link_unit = control_point.airdrome_id_for_landing  # type: ignore
                elif isinstance(control_point, Airfield):
                    waypoint.airdrome_id = control_point.airdrome_id_for_landing
                elif (pad := self.helipad_at(control_point)) is not None:
                    # A FOB or FARP. Without a pad to land on, the AI flies to
                    # the nearest airfield instead.
                    if len(self.group.units) > pad_spots(pad):
                        self.land_in_formation(waypoint, pad)
                    else:
                        waypoint.helipad_id = pad.id
                        waypoint.link_unit = pad.id
        return waypoint

    def land_in_formation(self, waypoint: MovingPoint, pad: BaseFARP) -> None:
        """Lands the whole group at the pad, off-pad where need be.

        DCS sends a group landing at a helipad to that one pad; members that
        find no free spot there fly back to the nearest airfield. A group too
        big for the pad lands with a land task instead, which sets everyone
        down in formation and keeps them there.
        """
        waypoint.type = "Turning Point"
        waypoint.action = PointAction.TurningPoint
        combat_landing = self.flight.coalition.game.settings.use_ai_combat_landing
        waypoint.add_task(
            Land(pad.position, duration=None, combat_landing=combat_landing)
        )

    def helipad_at(self, control_point: ControlPoint) -> Optional[BaseFARP]:
        """The helipad of control_point closest to its position, if any."""
        best: Optional[BaseFARP] = None
        best_distance = float(MAX_PAD_DISTANCE)
        for coalition in self.mission.coalition.values():
            for country in coalition.countries.values():
                for group in country.static_group:
                    for unit in group.units:
                        if not isinstance(unit, BaseFARP):
                            continue
                        distance = unit.position.distance_to_point(
                            control_point.position
                        )
                        if distance < best_distance:
                            best, best_distance = unit, distance
        return best
