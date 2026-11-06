"""The simulation of FARP setup flights (fast forward)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from dcs.mapping import Point
from dcs.terrain import Caucasus

from game.ato.flightplans.farpsetup import FarpSetupFlightPlan, FarpSetupLayout
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.sim import GameUpdateEvents
from game.theater.dynamicfarp import DynamicFarp

TERRAIN = Caucasus()


def waypoint(name: str, kind: FlightWaypointType) -> FlightWaypoint:
    return FlightWaypoint(name, kind, Point(0, 0, TERRAIN))


def make_plan(helicopter: bool) -> tuple[FarpSetupFlightPlan, Any]:
    setup = waypoint(
        "FARP SITE" if helicopter else "AIRDROP",
        (FlightWaypointType.DROPOFF_ZONE if helicopter else FlightWaypointType.NAV),
    )
    layout = FarpSetupLayout(
        departure=waypoint("TAKEOFF", FlightWaypointType.TAKEOFF),
        nav_to=[],
        setup=setup,
        nav_from=[],
        arrival=waypoint("LANDING", FlightWaypointType.LANDING_POINT),
        divert=None,
        bullseye=waypoint("BULLSEYE", FlightWaypointType.BULLSEYE),
        custom_waypoints=[],
    )
    flight: Any = MagicMock()
    farp = MagicMock(spec=DynamicFarp)
    farp.id = "farp-1"
    flight.package.target = farp
    return FarpSetupFlightPlan(flight, layout), flight


def test_helicopter_setup_flight_completes_where_it_lands() -> None:
    plan, _ = make_plan(helicopter=True)

    # Its route has no landing waypoint: the simulation must stop it at the site
    # rather than fly it on past the end of its route.
    assert plan.completes_at(plan.layout.setup)
    assert not plan.completes_at(plan.layout.bullseye)


def test_plane_setup_flight_completes_on_landing_back_home() -> None:
    plan, _ = make_plan(helicopter=False)

    assert not plan.completes_at(plan.layout.setup)
    assert plan.completes_at(plan.layout.arrival)


def test_reaching_the_site_in_fast_forward_delivers_the_equipment() -> None:
    for helicopter in (True, False):
        plan, flight = make_plan(helicopter)
        events = GameUpdateEvents()

        plan.on_waypoint_reached(plan.layout.departure, events)
        flight.coalition.farps.commit_setups.assert_not_called()

        plan.on_waypoint_reached(plan.layout.setup, events)
        flight.coalition.farps.commit_setups.assert_called_once_with(["farp-1"], events)
