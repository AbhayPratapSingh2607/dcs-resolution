"""Flight plan for flying in the equipment of a player-established FARP.

A helicopter lands at the FARP site and stays there; a transport plane runs in
low and airdrops the equipment over it, then flies home. The FARP is established once the mission reports that
this happened (see FarpSetupGenerator).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Type

from game.theater.dynamicfarp import AIRDROP_ALTITUDE, AIRDROP_MAX_AGL, DynamicFarp
from game.utils import feet, meters, nautical_miles
from .ibuilder import IBuilder
from .planningerror import PlanningError
from .standard import StandardFlightPlan, StandardLayout
from .waypointbuilder import WaypointBuilder
from ..flightwaypoint import FlightWaypoint
from ..flightwaypointtype import FlightWaypointType


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

            # Descend to drop altitude well before the site so the pass over it
            # is low and level, coming in from the departure side.
            heading = farp.position.heading_between_point(
                self.flight.departure.position
            )
            nav_to_end = farp.position.point_from_heading(
                heading, AIRDROP_RUN_IN.meters
            )
            run_in_point = builder.nav(
                nav_to_end, AIRDROP_ALTITUDE, altitude_is_agl=True
            )
            run_in_point.name = "RUN IN"
            run_in_point.description = (
                f"Descend to {AIRDROP_ALTITUDE.feet:.0f}ft AGL for the airdrop"
            )
            run_in_point.pretty_name = "Airdrop run-in"
            run_in.append(run_in_point)

        return FarpSetupLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, nav_to_end, altitude, helicopter
            )
            + run_in,
            setup=setup,
            nav_from=builder.nav_path(
                farp.position, self.flight.arrival.position, altitude, helicopter
            ),
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    def build(self, dump_debug_info: bool = False) -> FarpSetupFlightPlan:
        return FarpSetupFlightPlan(self.flight, self.layout())
