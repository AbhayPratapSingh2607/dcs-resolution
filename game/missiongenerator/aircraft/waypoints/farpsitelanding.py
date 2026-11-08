from dcs.point import MovingPoint
from dcs.task import Land

from .pydcswaypointbuilder import PydcsWaypointBuilder


class FarpSiteLandingBuilder(PydcsWaypointBuilder):
    """A FARP setup helicopter lands at the site and stays with the equipment."""

    def build(self) -> MovingPoint:
        waypoint = super().build()
        # Keep clear of the FARP's centre, where the pads will go.
        landing_point = waypoint.position.random_point_within(60, 30)
        combat_land = self.flight.coalition.game.settings.use_ai_combat_landing
        # Without a duration the helicopter lands and does not take off again.
        waypoint.add_task(
            Land(landing_point, duration=None, combat_landing=combat_land)
        )
        return waypoint
