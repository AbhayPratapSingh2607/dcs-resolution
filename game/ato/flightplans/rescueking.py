"""The Rescue King's C-130: an orbit over the spot the player placed the King.

The player places a Rescue King from the FARPs menu (FarpManager.establish_king).
It is an airborne DynamicFarp for one turn: two rescue helicopters are stationed
on it, start in the air over it, and AI helicopters leave the mission when they
come back to it. This flight plan is the C-130 circling it in the mission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING, Type

from dcs.mapping import Point

from game.ato.flightplans.ibuilder import IBuilder
from game.ato.flightplans.patrolling import PatrollingFlightPlan, PatrollingLayout
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.utils import Distance, Speed, feet, knots, meters, nautical_miles

if TYPE_CHECKING:
    from game.ato.flight import Flight
    from game.ato.flightwaypoint import FlightWaypoint

#: Half the length of the King's racetrack.
RACETRACK_HALF_LENGTH = nautical_miles(7.5)

#: The King's orbit altitude: low enough for the helicopters to join it.
KING_ALTITUDE = feet(10000)

#: How long the King is on station before the package TOT.
KING_LEAD = timedelta(minutes=20)

#: A tanker King (a KC-130) flies low and slow enough for helicopters to take
#: fuel from it: about 125 knots indicated at this altitude.
TANKER_KING_ALTITUDE = feet(6000)
TANKER_KING_SPEED = knots(135)


def is_tanker_king(flight: Flight) -> bool:
    """Whether this King flight refuels helicopters: its aircraft is a tanker."""
    from dcs.task import Refueling

    return Refueling in flight.unit_type.dcs_unit_type.tasks


@dataclass(frozen=True)
class KingOrbit:
    #: Centre of the racetrack: the spot the King was placed.
    center: Point
    #: The racetrack runs across this heading (toward the fight).
    heading: float

    @property
    def racetrack(self) -> tuple[Point, Point]:
        across = (self.heading + 90) % 360
        half = RACETRACK_HALF_LENGTH.meters
        return (
            self.center.point_from_heading(across, half),
            self.center.point_from_heading((across + 180) % 360, half),
        )


class RescueKingFlightPlan(PatrollingFlightPlan[PatrollingLayout]):
    @property
    def patrol_duration(self) -> timedelta:
        override = getattr(self.flight, "patrol_duration_override", None)
        if override is not None:
            return override
        settings = self.flight.coalition.game.settings
        return timedelta(minutes=settings.csar_king_on_station)

    @property
    def patrol_start_time(self) -> datetime:
        return self.tot - KING_LEAD

    @property
    def patrol_speed(self) -> Speed:
        if is_tanker_king(self.flight):
            return TANKER_KING_SPEED
        return self.flight.unit_type.preferred_patrol_speed(
            self.layout.patrol_start.alt
        )

    @property
    def engagement_distance(self) -> Distance:
        return meters(0)

    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder


class Builder(IBuilder[RescueKingFlightPlan, PatrollingLayout]):
    def layout(self) -> PatrollingLayout:
        from game.navmesh import NavMeshError
        from game.theater.dynamicfarp import is_rescue_king

        target = self.package.target
        heading: Optional[float] = None
        farp_heading = getattr(target, "farp_heading", None)
        if farp_heading is not None:
            heading = farp_heading.degrees
        orbit = KingOrbit(target.position, heading or 0.0)
        start, end = orbit.racetrack
        builder = WaypointBuilder(self.flight)
        tanker = is_tanker_king(self.flight)
        altitude = TANKER_KING_ALTITUDE if tanker else KING_ALTITUDE
        racetrack = builder.race_track(start, end, altitude)

        def route(a: Point, b: Point) -> list[FlightWaypoint]:
            # The King can sit inside the enemy's fighter coverage, which the
            # navmesh leaves out: fly straight in from the edge of safe airspace.
            try:
                return builder.nav_path(a, b, altitude)
            except NavMeshError:
                return []

        departure = builder.takeoff(self.flight.departure)
        if is_rescue_king(self.flight.departure):
            # The King's own tanker appears in the air over the King, at the
            # orbit's altitude.
            departure.alt = altitude
        arrival = builder.land(self.flight.arrival)
        if is_rescue_king(self.flight.arrival):
            # And leaves the mission there, still at the orbit's altitude.
            arrival.alt = altitude
        return PatrollingLayout(
            departure=departure,
            nav_to=route(self.flight.departure.position, start),
            nav_from=route(end, self.flight.arrival.position),
            patrol_start=racetrack[0],
            patrol_end=racetrack[1],
            arrival=arrival,
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    def build(self, dump_debug_info: bool = False) -> RescueKingFlightPlan:
        return RescueKingFlightPlan(self.flight, self.layout())
