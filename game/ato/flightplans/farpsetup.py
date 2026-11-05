"""Flight plan for flying in the equipment of a player-established FARP.

A helicopter lands at the FARP site; a transport plane airdrops the equipment
with a low pass over it. The FARP is established once the mission reports that
this happened (see FarpSetupGenerator).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Type

from game.theater.dynamicfarp import AIRDROP_ALTITUDE, AIRDROP_MAX_AGL, DynamicFarp
from game.utils import feet, meters
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

    def iter_waypoints(self) -> Iterator[FlightWaypoint]:
        yield self.departure
        yield from self.nav_to
        yield self.setup
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

        return FarpSetupLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, farp.position, altitude, helicopter
            ),
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
