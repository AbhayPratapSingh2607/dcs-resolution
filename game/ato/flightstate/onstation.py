"""The "On Station" start type: a flight that begins its mission already at
its station instead of starting at its departure base.

The station is the waypoint where the flight's work begins:

* patrolling flights (BARCAP, TARCAP, AEW&C, tankers, CAS): the start of the
  racetrack,
* fighter sweeps: the start of the sweep,
* attack packages and their escorts: the IP (ingress point),
* escorts of a patrolling flight (an AWACS or tanker escort): where they meet
  it at the package TOT, so they don't hold the package back,
* other formation flights: the join point, or the hold point.

Flights without one (ferry, transport, custom plans) start in the air over
their departure base, like the In Flight start type.

The flight appears at its station at the time its flight plan has it there.
If the package's TOT is set as soon as possible, that is mission start.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.starttype import StartType

if TYPE_CHECKING:
    from game.ato.flight import Flight
    from game.ato.flightplans.flightplan import FlightPlan
    from game.ato.flightwaypoint import FlightWaypoint
    from game.settings import Settings

    from .inflight import InFlight

#: Layout waypoints that can serve as the station, in order of preference, for
#: flight plans that aren't patrols.
STATION_WAYPOINTS = ("sweep_start", "ingress", "join", "hold")

ESCORT_TYPES = {FlightType.ESCORT, FlightType.SEAD_ESCORT}

#: Step for simulating a flight from its station time up to mission start.
STEP = timedelta(seconds=5)


def station_waypoint(flight_plan: FlightPlan[Any]) -> Optional[FlightWaypoint]:
    """Where an On Station flight begins, or None if its plan has no station."""
    layout = flight_plan.layout
    candidates: list[Optional[FlightWaypoint]] = []
    if _escorts_patrol(flight_plan.flight):
        candidates.append(flight_plan.tot_waypoint)
    if flight_plan.is_patrol(flight_plan):
        candidates.append(getattr(layout, "patrol_start", None))
    candidates.extend(getattr(layout, name, None) for name in STATION_WAYPOINTS)
    waypoints = flight_plan.waypoints
    for waypoint in candidates:
        # The station must be followed by another waypoint to fly to.
        if waypoint is not None and waypoint in waypoints[:-1]:
            return waypoint
    return None


def _escorts_patrol(flight: Flight) -> bool:
    if flight.flight_type not in ESCORT_TYPES:
        return False
    primary = flight.package.primary_flight
    if primary is None or primary is flight:
        return False
    return primary.flight_plan.is_patrol(primary.flight_plan)


def starts_on_station(flight: Flight) -> bool:
    """Whether the flight starts at a station (rather than over its base)."""
    return (
        flight.start_type is StartType.ON_STATION
        and station_waypoint(flight.flight_plan) is not None
    )


def station_time(flight_plan: FlightPlan[Any]) -> datetime:
    """When the flight plan has the flight at its station."""
    station = station_waypoint(flight_plan)
    assert station is not None
    return flight_plan.takeoff_time() + flight_plan._travel_time_to_waypoint(station)


def duration_from_station_to_tot(flight_plan: FlightPlan[Any]) -> timedelta:
    station = station_waypoint(flight_plan)
    assert station is not None
    tot_waypoint = flight_plan.tot_waypoint
    return max(
        timedelta(),
        flight_plan._travel_time_to_waypoint(tot_waypoint)
        - flight_plan._travel_time_to_waypoint(station),
    )


def station_state(flight: Flight, settings: Settings) -> InFlight:
    """The flight's state on arriving at its station."""
    from .loiter import Loiter
    from .navigating import Navigating
    from .racetrack import RaceTrack

    station = station_waypoint(flight.flight_plan)
    assert station is not None
    index = flight.flight_plan.waypoints.index(station)
    if station.waypoint_type is FlightWaypointType.PATROL_TRACK:
        return RaceTrack(flight, settings, index)
    if station.waypoint_type is FlightWaypointType.LOITER:
        return Loiter(flight, settings, index)
    return Navigating(flight, settings, index)


def advance_to(flight: Flight, start: datetime, now: datetime) -> None:
    """Simulate the flight from start (when it was at its station) up to now,
    without combat, so a flight that should already be further along is."""
    from game.sim.gameupdateevents import GameUpdateEvents

    from .completed import Completed

    events = GameUpdateEvents()
    time = start
    while time < now:
        step = min(STEP, now - time)
        time += step
        flight.on_game_tick(events, time, step)
        if isinstance(flight.state, Completed) or not flight.state.alive:
            return
