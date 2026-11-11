"""What AI flights achieve when the combat model flies them instead of DCS (V4).

In a full turn most flights never enter the DCS mission: they fly before the
window, outside the bubble or after it. Some missions only take effect
through an in-mission script: Ops.CSAR reports rescues, CTLD reports FARP
deliveries and capture triggers report bases taken. For flights the mission
never had, these results are credited here instead, when the flight survived:

* a FARP setup flight delivers its FARP's equipment;
* an air assault takes its objective if nothing defends it any more (no
  armor left at the base), like a capture in the fast forward.

CSAR has its own fallback in MissionResultsProcessor.commit_csar_results.
"""

from __future__ import annotations

import logging
from typing import Iterator, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato.flight import Flight
    from game.debriefing import BaseCaptureEvent, Debriefing


def ai_flights_outside_mission(
    game: Game, debriefing: Debriefing, flight_type: FlightType
) -> Iterator[Flight]:
    """Surviving AI flights of ``flight_type`` that weren't in the mission."""
    flown = {entry.flight for entry in debriefing.unit_map.aircraft.values()}
    for coalition in game.coalitions:
        for package in coalition.ato.packages:
            for flight in package.flights:
                if flight.flight_type is not flight_type:
                    continue
                if flight.client_count > 0 or flight in flown:
                    # Player-flown or in the mission: the mission's report is
                    # what counts.
                    continue
                if debriefing.air_losses.surviving_flight_members(flight) <= 0:
                    continue
                yield flight


def farp_deliveries(game: Game, debriefing: Debriefing) -> list[str]:
    """Ids of FARPs whose setup flight flew outside the mission and survived."""
    from game.theater.dynamicfarp import DynamicFarp

    delivered: list[str] = []
    for flight in ai_flights_outside_mission(game, debriefing, FlightType.TRANSPORT):
        target = flight.package.target
        if isinstance(target, DynamicFarp) and not target.established:
            logging.info(
                "%s delivered %s's equipment outside the mission", flight, target.name
            )
            delivered.append(str(target.id))
    return delivered


def air_assault_captures(game: Game, debriefing: Debriefing) -> list[BaseCaptureEvent]:
    """Bases taken by air assaults flown outside the mission: the troops land
    and the base falls if it has no armor left to hold it."""
    from game.debriefing import BaseCaptureEvent
    from game.theater.controlpoint import ControlPoint

    reported = {c.control_point.id for c in debriefing.base_captures}
    captures: list[BaseCaptureEvent] = []
    for flight in ai_flights_outside_mission(game, debriefing, FlightType.AIR_ASSAULT):
        target = flight.package.target
        if not isinstance(target, ControlPoint) or target.id in reported:
            continue
        attacker = flight.squadron.player
        if target.captured == attacker or target.captured.is_neutral:
            continue
        if target.is_fleet or target.base.total_armor > 0:
            logging.info(
                "%s landed at %s outside the mission; its defenders hold it",
                flight,
                target.name,
            )
            continue
        logging.info(
            "%s takes %s outside the mission: nothing defends it", flight, target
        )
        reported.add(target.id)
        captures.append(BaseCaptureEvent(target, attacker))
    return captures
