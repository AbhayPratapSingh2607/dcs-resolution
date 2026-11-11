from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from game.ato.flighttype import FlightType
from game.ato.flightstate import InFlight
from game.ato.flightstate.killed import Killed
from game.server.leaflet import LeafletPoint
from game.server.waypoints.models import FlightWaypointJs
from game.server.waypoints.routes import waypoints_for_flight

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight


#: Tasks flown as routine lines (W4): on the map they are a station symbol,
#: not a route, unless selected.
ROUTINE_TASKS = {
    FlightType.BARCAP,
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.RECOVERY,
}


def routine_station(flight: Flight) -> Optional[tuple[str, Any]]:
    """(label, position) of the station a routine flight holds, or None for
    a flight that isn't a routine line: a package with players, a strike,
    or a support flight inside a strike package."""
    package = flight.package
    if package is None or package.has_players:
        return None
    alert = bool(getattr(flight, "alert", False))
    if not alert and flight.flight_type not in ROUTINE_TASKS:
        return None
    if not alert and any(
        f.flight_type not in ROUTINE_TASKS and not getattr(f, "alert", False)
        for f in package.flights
    ):
        return None
    position = None
    try:
        position = flight.flight_plan.layout.patrol_start.position
    except Exception:
        position = None
    if position is None:
        position = package.target.position
    label = (
        f"Ground alert {flight.departure.name}"
        if alert
        else f"{flight.flight_type.value} {package.target.name}"
    )
    return label, position


class FlightJs(BaseModel):
    id: UUID
    blue: bool
    position: LeafletPoint | None
    sidc: str
    waypoints: list[FlightWaypointJs] | None
    #: A routine line (CAP, AWACS, tanker, ground alert): drawn as a station
    #: symbol instead of a route until selected.
    routine: bool = False
    station: LeafletPoint | None = None
    label: str | None = None
    #: Outside the bubble (M3): fought by the combat model, drawn dimmed.
    elsewhere: bool = False

    class Config:
        title = "Flight"

    @staticmethod
    def for_flight(flight: Flight, with_waypoints: bool) -> FlightJs:
        # Don't provide a location for aircraft that aren't in the air. Later we can
        # expand the model to include the state data for the UI so that it can make its
        # own decisions about whether to draw the aircraft, but for now we'll filter
        # here.
        #
        # We also draw dead aircraft so the player has some feedback about what's being
        # lost.
        from game.server.fogofwar import flight_visible, show_flight_routes

        game = getattr(getattr(flight, "coalition", None), "game", None)
        position = None
        if isinstance(flight.state, InFlight) or isinstance(flight.state, Killed):
            if flight_visible(game, flight):
                position = flight.position().latlng()
        waypoints = None
        routine = False
        station = None
        label = None
        if with_waypoints and show_flight_routes(game, flight):
            waypoints = waypoints_for_flight(flight)
            found = routine_station(flight)
            if found is not None:
                routine = True
                label, point = found
                try:
                    station = LeafletPoint.from_latlng(point.latlng())
                except Exception:
                    station = None
        if flight.blue.is_blue:
            blue = True
        else:
            blue = False
        elsewhere = False
        if waypoints is not None and game is not None:
            try:
                from game.sim.bubble import elsewhere_ids, is_elsewhere

                elsewhere = is_elsewhere(flight.package) or id(
                    flight.package
                ) in elsewhere_ids(game)
            except Exception:
                elsewhere = False
        return FlightJs(
            id=flight.id,
            blue=blue,
            position=position,
            sidc=str(flight.sidc()),
            waypoints=waypoints,
            routine=routine,
            station=station,
            label=label,
            elsewhere=elsewhere,
        )

    @staticmethod
    def all_in_game(game: Game, with_waypoints: bool) -> list[FlightJs]:
        flights = []
        for coalition in game.coalitions:
            for package in coalition.ato.packages:
                for flight in package.flights:
                    flights.append(FlightJs.for_flight(flight, with_waypoints))
        return flights
