"""Road bases: flying on when the home runway is cratered.

Air forces that expect war plan to keep flying from highway strips, taxiways
and dispersal sites when their main runways are cut (the Swedish Bas 90
system, Soviet and Russian highway strips, Ukraine in 2022). Here a squadron
at an airfield whose runway is out of action can still fly part of its
aircraft: they "took off from a road base" and appear in the air a few miles
from their airfield, in DCS and in the combat model alike.

How much of a squadron can fly that way (``road_share``) depends on how ready
the side was:

* red at the opening follows the strategic surprise: with no surprise it had
  dispersed and prepared its road strips, with full surprise it is caught at
  its main bases. Each turn after the first it organises a little more.
* red once organised flies a steady share.

Only red flies from road bases: a cratered blue runway grounds everything
there.

Helicopters don't need a runway, so they all fly. Aircraft too big for a road
(bombers, tankers, AWACS, transports) don't.

The setting "Road base operations" turns this off: a cratered runway then
grounds everything there, as before.
"""

from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight
    from game.squadrons import Squadron
    from game.theater import ControlPoint
    from game.theater.player import Player

#: Share of a squadron that flies from road bases once red is organised.
ORGANISED_SHARE = 0.4
#: Red's share on turn 1 by strategic surprise (game.opening.Surprise name).
OPENING_SHARE = {"NONE": 0.5, "PARTIAL": 0.25, "FULL": 0.1}
#: How much red's share grows each turn after the first, up to the larger of
#: its opening share and ORGANISED_SHARE.
GROWTH_PER_TURN = 0.1

#: Squadrons whose primary task says they are too big for a road strip.
LARGE_AIRCRAFT_TASKS = {
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.TRANSPORT,
}
#: Strategic bombers, by variant id (game.opening.BOMBER_KEYS).
BOMBER_KEYS = ("B-52", "B-1B", "B_1", "Tu-95", "Tu-160", "Tu-22")


def enabled(game: Game) -> bool:
    return bool(getattr(game.settings, "road_base_operations", True))


def road_share(game: Game, player: Player) -> float:
    """Share of a capable squadron's aircraft that can fly from road bases.
    Blue doesn't fly from road bases."""
    if player.is_blue:
        return 0.0
    from game.opening import opening_of, surprise_of

    if not opening_of(game).begun:
        return ORGANISED_SHARE
    start = OPENING_SHARE.get(surprise_of(game).name, ORGANISED_SHARE)
    turns_since = max(0, int(getattr(game, "turn", 1)) - 1)
    ceiling = max(start, ORGANISED_SHARE)
    return min(ceiling, start + GROWTH_PER_TURN * turns_since)


def is_road_base(control_point: ControlPoint) -> bool:
    """Whether the base's squadrons fly from road bases now: a land airfield
    whose runway is out of action, held by red, with the setting on."""
    from game.theater.controlpoint import Airfield

    if not isinstance(control_point, Airfield):
        return False
    if control_point.captured.is_blue:
        return False
    if control_point.runway_is_operational():
        return False
    game = control_point.coalition.game
    return enabled(game)


def road_capable(squadron: Squadron) -> bool:
    aircraft = squadron.aircraft
    if aircraft.helicopter:
        return True
    if squadron.primary_task in LARGE_AIRCRAFT_TASKS:
        return False
    variant = str(getattr(aircraft, "variant_id", ""))
    return not any(key in variant for key in BOMBER_KEYS)


def road_capacity(squadron: Squadron) -> Optional[int]:
    """Aircraft of the squadron that can fly this turn from road bases, or None
    when its base isn't a road base (no limit from this)."""
    location = getattr(squadron, "location", None)
    if location is None or not is_road_base(location):
        return None
    if not road_capable(squadron):
        return 0
    untasked = max(0, squadron.untasked_aircraft)
    if squadron.aircraft.helicopter:
        return untasked
    share = road_share(location.coalition.game, squadron.player)
    return min(untasked, math.floor(untasked * share + 1e-9))


def flies_from_road(squadron: Squadron) -> bool:
    return bool(road_capacity(squadron))


def mark_road_base_flight(flight: Flight) -> bool:
    """A flight from a squadron on a road base takes off from the road: it
    starts in the air near its airfield. Returns whether it does."""
    from game.ato.starttype import StartType

    if not is_road_base(flight.squadron.location):
        flight.from_road_base = False
        return False
    flight.from_road_base = True
    flight.start_type = StartType.IN_FLIGHT
    return True
