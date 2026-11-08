"""The On Station start type."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

from dcs import Point
from dcs.terrain import Caucasus

from game.ato.flightstate import Navigating, Uninitialized, WaitingForStart
from game.ato.flightstate.flightstate import FlightState
from game.ato.flightstate.onstation import (
    duration_from_station_to_tot,
    starts_on_station,
    station_time,
    station_waypoint,
)
from game.ato.flighttype import FlightType
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as T
from game.ato.starttype import StartType

NOW = datetime(2010, 6, 1, 8, 0)
TERRAIN = Caucasus()
#: Every leg takes ten minutes.
LEG = timedelta(minutes=10)


def _wp(name: str, kind: T, x_km: float) -> FlightWaypoint:
    return FlightWaypoint(name, kind, Point(x_km * 1000, 0, TERRAIN))


class FakePlan:
    """A flight plan with a straight route and ten minute legs."""

    def __init__(
        self,
        flight: Any,
        layout: Any,
        waypoints: list[FlightWaypoint],
        tot_waypoint: FlightWaypoint,
        tot: datetime = NOW + timedelta(hours=1),
        patrol: bool = False,
    ) -> None:
        self.flight = flight
        self.layout = layout
        self.waypoints = waypoints
        self.tot_waypoint = tot_waypoint
        self.tot = tot
        self.patrol = patrol

    def is_patrol(self, plan: Any) -> bool:
        return self.patrol

    def _travel_time_to_waypoint(self, waypoint: FlightWaypoint) -> timedelta:
        return LEG * self.waypoints.index(waypoint)

    def travel_time_between_waypoints(self, a: Any, b: Any) -> timedelta:
        return LEG

    def takeoff_time(self) -> datetime:
        return self.tot - self._travel_time_to_waypoint(self.tot_waypoint)

    def startup_time(self) -> datetime:
        if starts_on_station(self.flight):
            return station_time(self)  # type: ignore[arg-type]
        return self.takeoff_time()


class FakeFlight:
    def __init__(self, task: FlightType = FlightType.STRIKE) -> None:
        self.flight_type = task
        self.start_type = StartType.ON_STATION
        self.package = SimpleNamespace(primary_flight=self)
        self.flight_plan: Any = None
        self.state: Optional[FlightState] = None

    def set_state(self, state: FlightState) -> None:
        self.state = state

    def on_game_tick(self, events: Any, time: datetime, duration: timedelta) -> None:
        assert self.state is not None
        self.state.on_game_tick(events, time, duration)


def _strike(tot: datetime = NOW + timedelta(hours=1)) -> FakeFlight:
    departure = _wp("TAKEOFF", T.TAKEOFF, 0)
    hold = _wp("HOLD", T.LOITER, 10)
    join = _wp("JOIN", T.JOIN, 20)
    ingress = _wp("INGRESS", T.INGRESS_STRIKE, 30)
    target = _wp("TARGET", T.TARGET_POINT, 40)
    split = _wp("SPLIT", T.SPLIT, 50)
    landing = _wp("LANDING", T.LANDING_POINT, 60)
    flight = FakeFlight()
    layout = SimpleNamespace(hold=hold, join=join, ingress=ingress)
    flight.flight_plan = FakePlan(
        flight,
        layout,
        [departure, hold, join, ingress, target, split, landing],
        target,
        tot,
    )
    return flight


def _patrol(task: FlightType = FlightType.BARCAP) -> FakeFlight:
    departure = _wp("TAKEOFF", T.TAKEOFF, 0)
    nav = _wp("NAV", T.NAV, 20)
    start = _wp("RACETRACK START", T.PATROL_TRACK, 40)
    end = _wp("RACETRACK END", T.PATROL, 60)
    landing = _wp("LANDING", T.LANDING_POINT, 0)
    flight = FakeFlight(task)
    layout = SimpleNamespace(patrol_start=start, join=None, hold=None)
    flight.flight_plan = FakePlan(
        flight, layout, [departure, nav, start, end, landing], start, patrol=True
    )
    return flight


def test_station_is_the_racetrack_ip_or_join() -> None:
    patrol = _patrol()
    assert station_waypoint(patrol.flight_plan).name == "RACETRACK START"  # type: ignore[union-attr]
    strike = _strike()
    assert station_waypoint(strike.flight_plan).name == "INGRESS"  # type: ignore[union-attr]
    strike.flight_plan.layout.ingress = None
    assert station_waypoint(strike.flight_plan).name == "JOIN"  # type: ignore[union-attr]

    # Ferry-like plans have no station and start over their base instead.
    ferry = _strike()
    ferry.flight_plan.layout = SimpleNamespace()
    assert station_waypoint(ferry.flight_plan) is None
    assert not starts_on_station(ferry)  # type: ignore[arg-type]


def test_escort_of_a_patrol_starts_where_it_meets_it() -> None:
    awacs = _patrol(FlightType.AEWC)
    escort = _strike()
    escort.flight_type = FlightType.ESCORT
    escort.package = awacs.package
    assert station_waypoint(escort.flight_plan).name == "TARGET"  # type: ignore[union-attr]


def test_station_timing() -> None:
    strike = _strike(tot=NOW + timedelta(hours=1))
    plan: Any = strike.flight_plan
    # Target at TOT, the IP one leg before.
    assert station_time(plan) == NOW + timedelta(minutes=50)
    assert duration_from_station_to_tot(plan) == LEG
    # A patrol is on station at its TOT.
    patrol: Any = _patrol().flight_plan
    assert station_time(patrol) == patrol.tot
    assert duration_from_station_to_tot(patrol) == timedelta()


def test_flight_appears_at_its_station() -> None:
    settings: Any = SimpleNamespace()
    # Station time after mission start: waits, then appears at the IP.
    later = _strike(tot=NOW + timedelta(hours=1))
    Uninitialized(later, settings).reinitialize(NOW)  # type: ignore[arg-type]
    assert isinstance(later.state, WaitingForStart)
    assert later.state.start_time == NOW + timedelta(minutes=50)
    later.state.on_game_tick(None, NOW + timedelta(minutes=50), timedelta(seconds=1))  # type: ignore[arg-type]
    assert isinstance(later.state, Navigating)
    assert later.state.current_waypoint.name == "INGRESS"

    # Station time at mission start: on station immediately.
    now = _strike(tot=NOW + LEG)
    Uninitialized(now, settings).reinitialize(NOW)  # type: ignore[arg-type]
    assert isinstance(now.state, Navigating)
    assert now.state.current_waypoint.name == "INGRESS"
    assert now.state.spawn_type is StartType.IN_FLIGHT

    # Station time before mission start: already further along.
    early = _strike(tot=NOW + timedelta(minutes=5))
    Uninitialized(early, settings).reinitialize(NOW)  # type: ignore[arg-type]
    assert isinstance(early.state, Navigating)
    assert early.state.current_waypoint.name == "INGRESS"
    assert early.state.elapsed_time == timedelta(minutes=5)
