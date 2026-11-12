"""Where a simulated flight's mission ends."""

from types import SimpleNamespace

from dcs import Point
from dcs.terrain import Caucasus

from game.ato.flightplans.flightplan import FlightPlan
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as T

TERRAIN = Caucasus()


def _wp(name: str, kind: T) -> FlightWaypoint:
    return FlightWaypoint(name, kind, Point(0, 0, TERRAIN))


def test_flight_to_an_off_map_base_completes_at_its_exit_point() -> None:
    # WaypointBuilder.land makes the arrival of an off-map base a NAV point.
    exit_point = _wp("NAV", T.NAV)
    nav = _wp("NAV", T.NAV)
    plan = SimpleNamespace(layout=SimpleNamespace(arrival=exit_point))
    assert FlightPlan.completes_at(plan, exit_point)  # type: ignore[arg-type]
    assert not FlightPlan.completes_at(plan, nav)  # type: ignore[arg-type]
    assert not FlightPlan.completes_at(plan, _wp("BULLSEYE", T.BULLSEYE))  # type: ignore[arg-type]


def test_landing_point_completes() -> None:
    plan = SimpleNamespace(layout=SimpleNamespace())
    assert FlightPlan.completes_at(plan, _wp("LANDING", T.LANDING_POINT))  # type: ignore[arg-type]
