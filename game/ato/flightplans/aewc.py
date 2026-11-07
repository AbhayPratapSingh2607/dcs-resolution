from __future__ import annotations

import logging
from datetime import timedelta
from typing import Type

from dcs.mapping import Point

from game.ato.flightplans.ibuilder import IBuilder
from game.ato.flightplans.patrolling import PatrollingFlightPlan, PatrollingLayout
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.utils import Distance, Heading, Speed, knots, meters, nautical_miles


class AewcFlightPlan(PatrollingFlightPlan[PatrollingLayout]):
    @property
    def patrol_duration(self) -> timedelta:
        return self.flight.coalition.game.settings.desired_awacs_mission_duration

    @property
    def patrol_speed(self) -> Speed:
        altitude = self.layout.patrol_start.alt
        if self.flight.unit_type.preferred_patrol_speed(altitude) is not None:
            return self.flight.unit_type.preferred_patrol_speed(altitude)
        return knots(390)

    @property
    def engagement_distance(self) -> Distance:
        # TODO: Factor out a common base of the combat and non-combat race-tracks.
        # No harm in setting this, but we ought to clean up a bit.
        return meters(0)

    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder


class Builder(IBuilder[AewcFlightPlan, PatrollingLayout]):
    def layout(self) -> PatrollingLayout:
        racetrack_half_distance = nautical_miles(30).meters

        location = self.package.target

        closest_boundary = self.threat_zones.closest_boundary(location.position)
        heading_to_threat_boundary = Heading.from_degrees(
            location.position.heading_between_point(closest_boundary)
        )
        distance_to_threat = meters(
            location.position.distance_to_point(closest_boundary)
        )
        orbit_heading = heading_to_threat_boundary

        # Station 80nm outside the threat zone.
        threat_buffer = nautical_miles(
            self.coalition.game.settings.aewc_threat_buffer_min_distance
        )
        if self.threat_zones.threatened(location.position):
            orbit_distance = distance_to_threat + threat_buffer
        else:
            orbit_distance = distance_to_threat - threat_buffer

        racetrack_start, racetrack_end = self._racetrack_on_navmesh(
            location.position,
            orbit_heading,
            orbit_distance,
            racetrack_half_distance,
        )

        builder = WaypointBuilder(self.flight)

        altitude = builder.get_patrol_altitude

        racetrack = builder.race_track(racetrack_start, racetrack_end, altitude)

        return PatrollingLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, racetrack_start, altitude
            ),
            nav_from=builder.nav_path(
                racetrack_end, self.flight.arrival.position, altitude
            ),
            patrol_start=racetrack[0],
            patrol_end=racetrack[1],
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    #: How many positions between the ideal orbit and the target are tried when
    #: the ideal orbit doesn't fit on the navmesh.
    ORBIT_PULLBACK_STEPS = 20

    def _racetrack_on_navmesh(
        self,
        origin: Point,
        orbit_heading: Heading,
        orbit_distance: Distance,
        racetrack_half_distance: float,
    ) -> tuple[Point, Point]:
        """The racetrack's start and end, both on the coalition's navmesh.

        The ideal orbit stands off the threat boundary by the AEW&C buffer. When
        the target is deep inside the enemy's threat zone, that can put the orbit
        beyond the edge of the navmesh, where no route can reach it. In that case
        the orbit is pulled back towards the target until both ends of the
        racetrack can be reached, which trades some of the stand-off distance for a
        plannable mission. If no such position exists, the ideal orbit is returned
        and routing to it fails as before.
        """
        navmesh = self.coalition.nav_mesh

        def racetrack_at(distance: float) -> tuple[Point, Point]:
            center = origin.point_from_heading(orbit_heading.degrees, distance)
            return (
                center.point_from_heading(
                    orbit_heading.right.degrees, racetrack_half_distance
                ),
                center.point_from_heading(
                    orbit_heading.left.degrees, racetrack_half_distance
                ),
            )

        ideal = racetrack_at(orbit_distance.meters)
        for step in range(self.ORBIT_PULLBACK_STEPS + 1):
            distance = orbit_distance.meters * (1 - step / self.ORBIT_PULLBACK_STEPS)
            start, end = racetrack_at(distance)
            if (
                navmesh.localize(start) is not None
                and navmesh.localize(end) is not None
            ):
                if step:
                    logging.warning(
                        f"AEW&C orbit for {self.package.target} pulled back from "
                        f"{orbit_distance.nautical_miles:.0f}nm to "
                        f"{meters(distance).nautical_miles:.0f}nm to stay on the "
                        "navmesh"
                    )
                return start, end
        return ideal

    def build(self, dump_debug_info: bool = False) -> AewcFlightPlan:
        return AewcFlightPlan(self.flight, self.layout())
