"""Flight plan for flying in the equipment of a player-established FARP.

A helicopter lands at the FARP site and stays there; a transport plane climbs to
cruise altitude, descends near the site, runs in low and airdrops the equipment
over it, then climbs back to cruise altitude and flies home. The FARP is established once the mission reports that
this happened (see FarpSetupGenerator), or as soon as the flight gets there if
that's already in the past when the mission starts (fast forward).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Type

from dcs.mapping import Point

from game.theater.dynamicfarp import AIRDROP_ALTITUDE, AIRDROP_MAX_AGL, DynamicFarp
from game.utils import Distance, feet, meters, nautical_miles
from .ibuilder import IBuilder
from .planningerror import PlanningError
from .standard import StandardFlightPlan, StandardLayout
from .waypointbuilder import WaypointBuilder
from ..flightwaypoint import FlightWaypoint
from ..flightwaypointtype import FlightWaypointType

if TYPE_CHECKING:
    from game.sim import GameUpdateEvents


@dataclass
class FarpSetupLayout(StandardLayout):
    #: Where the helicopter lands, or the plane makes its airdrop pass.
    setup: FlightWaypoint

    @property
    def stays_at_site(self) -> bool:
        """Whether the flight lands at the FARP and stays (a helicopter)."""
        return self.setup.waypoint_type is FlightWaypointType.DROPOFF_ZONE

    def iter_waypoints(self) -> Iterator[FlightWaypoint]:
        yield self.departure
        yield from self.nav_to
        yield self.setup
        if self.stays_at_site:
            # The helicopter stays with the equipment; the route ends here.
            yield self.bullseye
            yield from self.custom_waypoints
            return
        yield from self.nav_from
        yield self.arrival
        if self.divert is not None:
            yield self.divert
        yield self.bullseye
        yield from self.custom_waypoints


class FarpSetupFlightPlan(StandardFlightPlan[FarpSetupLayout]):
    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    @property
    def tot_waypoint(self) -> FlightWaypoint:
        return self.layout.setup

    def tot_for_waypoint(self, waypoint: FlightWaypoint) -> datetime | None:
        # Like other transport flights, these fly as soon as they can.
        return None

    def completes_at(self, waypoint: FlightWaypoint) -> bool:
        # A helicopter's route ends where it lands at the site; it has no landing
        # waypoint.
        if waypoint is self.layout.setup and self.layout.stays_at_site:
            return True
        return super().completes_at(waypoint)

    def on_waypoint_reached(
        self, waypoint: FlightWaypoint, events: GameUpdateEvents
    ) -> None:
        """Delivers the equipment when the fast-forwarded flight reaches the site.

        That happens before the mission starts, so the mission can't report it:
        the flight is spawned past the site (or, landed, not at all).
        """
        farp = self.package.target
        if waypoint is self.layout.setup and isinstance(farp, DynamicFarp):
            self.flight.coalition.farps.commit_setups([str(farp.id)], events)

    def depart_time_for_waypoint(self, waypoint: FlightWaypoint) -> datetime | None:
        return None

    @property
    def mission_begin_on_station_time(self) -> datetime | None:
        return None

    @property
    def mission_departure_time(self) -> datetime:
        return self.package.time_over_target


def is_farp_setup_target(target: object) -> bool:
    """Whether a package target is a FARP still waiting for its equipment."""
    return isinstance(target, DynamicFarp) and not target.established


#: How far before the site a plane starts its low, level airdrop run.
AIRDROP_RUN_IN = nautical_miles(4)

#: How far before the run-in a plane leaves cruise altitude, per 1000ft of
#: cruise altitude, and at least.
DESCENT_PER_1000FT = nautical_miles(2)
MIN_DESCENT_DISTANCE = nautical_miles(10)

#: How far a plane flies from the airfield or the site while climbing to cruise
#: altitude, at most.
MAX_CLIMB_DISTANCE = nautical_miles(10)


def descent_distance(cruise: Distance) -> Distance:
    """How far before the run-in a plane at `cruise` starts its descent."""
    return max(
        MIN_DESCENT_DISTANCE, meters(DESCENT_PER_1000FT.meters * cruise.feet / 1000)
    )


class Builder(IBuilder[FarpSetupFlightPlan, FarpSetupLayout]):
    def layout(self) -> FarpSetupLayout:
        farp = self.package.target
        if not isinstance(farp, DynamicFarp):
            raise PlanningError("FARP setup flights must target a FARP.")

        builder = WaypointBuilder(self.flight)
        helicopter = self.flight.is_helo
        altitude = (
            feet(self.coalition.game.settings.heli_cruise_alt_agl)
            if helicopter
            else builder.get_cruise_altitude
        )

        nav_to_end = farp.position
        run_in: list[FlightWaypoint] = []
        if helicopter:
            setup = FlightWaypoint(
                "FARP SITE",
                FlightWaypointType.DROPOFF_ZONE,
                farp.position,
                meters(0),
                "RADIO",
                description=f"Land at {farp.name} to set up the FARP",
                pretty_name="FARP site",
            )
        else:
            setup = builder.nav(farp.position, AIRDROP_ALTITUDE, altitude_is_agl=True)
            setup.name = "AIRDROP"
            setup.description = (
                f"Airdrop the FARP equipment: pass over {farp.name} below "
                f"{AIRDROP_MAX_AGL.feet:.0f}ft AGL"
            )
            setup.pretty_name = "Airdrop"
            setup.flyover = True

            # Fly at cruise altitude and descend near the site, reaching drop
            # altitude well before it so the pass over it is low and level,
            # coming in from the departure side.
            departure = self.flight.departure.position
            heading = farp.position.heading_between_point(departure)
            total = farp.position.distance_to_point(departure)
            climb = min(MAX_CLIMB_DISTANCE.meters, total / 4)
            nav_from_start = self._cruise_point(
                builder,
                farp.position.point_from_heading(
                    farp.position.heading_between_point(self.flight.arrival.position),
                    min(
                        MAX_CLIMB_DISTANCE.meters,
                        farp.position.distance_to_point(self.flight.arrival.position)
                        / 4,
                    ),
                ),
                altitude,
                "CLIMB OUT",
                "Climb back to cruise altitude",
            )
            ascent = self._cruise_point(
                builder,
                departure.point_from_heading(
                    departure.heading_between_point(farp.position), climb
                ),
                altitude,
                "CLIMB",
                "Climb to cruise altitude",
            )
            descent_from_site = min(
                AIRDROP_RUN_IN.meters + descent_distance(altitude).meters,
                total - climb,
            )
            nav_to_end = ascent.position
            if descent_from_site > AIRDROP_RUN_IN.meters:
                descent = self._cruise_point(
                    builder,
                    farp.position.point_from_heading(heading, descent_from_site),
                    altitude,
                    "DESCENT",
                    f"Descend to {AIRDROP_ALTITUDE.feet:.0f}ft AGL for the airdrop",
                )
                nav_to_end = descent.position
                run_in.append(descent)

            run_in_point = builder.nav(
                farp.position.point_from_heading(heading, AIRDROP_RUN_IN.meters),
                AIRDROP_ALTITUDE,
                altitude_is_agl=True,
            )
            run_in_point.name = "RUN IN"
            run_in_point.description = (
                f"At {AIRDROP_ALTITUDE.feet:.0f}ft AGL, run in to the airdrop"
            )
            run_in_point.pretty_name = "Airdrop run-in"
            run_in.append(run_in_point)

        if helicopter:
            nav_to = builder.nav_path(
                self.flight.departure.position, nav_to_end, altitude, helicopter
            )
            nav_from = builder.nav_path(
                farp.position, self.flight.arrival.position, altitude, helicopter
            )
        else:
            nav_to = [ascent]
            if nav_to_end != ascent.position:
                nav_to += builder.nav_path(ascent.position, nav_to_end, altitude)
            nav_to += run_in
            nav_from = [nav_from_start] + builder.nav_path(
                nav_from_start.position, self.flight.arrival.position, altitude
            )

        return FarpSetupLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=nav_to,
            setup=setup,
            nav_from=nav_from,
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    @staticmethod
    def _cruise_point(
        builder: WaypointBuilder,
        position: Point,
        altitude: Distance,
        name: str,
        description: str,
    ) -> FlightWaypoint:
        point = builder.nav(position, altitude)
        point.name = name
        point.description = description
        point.pretty_name = name.capitalize()
        return point

    def build(self, dump_debug_info: bool = False) -> FarpSetupFlightPlan:
        return FarpSetupFlightPlan(self.flight, self.layout())
