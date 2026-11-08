"""What the player (blue) is allowed to see of the enemy on the map.

The map is the player's view, so enemy objects are shown from blue's
intelligence picture (game.warfare.intel) according to the fog of war
setting:

* Off: everything, exactly, as before.
* Soft: every enemy site is shown, but sites blue hasn't confirmed are marked
  unconfirmed and their units and ranges are hidden.
* Strict: only sites blue knows about, at the position blue believes, with an
  uncertainty ring, and without units or ranges until confirmed.

Enemy flights are shown only while blue radar coverage (EWRs, AWACS) can see
them, and never with their routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from game.settings.settings import FogOfWar
from game.theater.player import Player

if TYPE_CHECKING:
    from dcs import Point

    from game import Game
    from game.ato import Flight
    from game.theater import TheaterGroundObject


@dataclass(frozen=True)
class TgoView:
    known: bool
    confirmed: bool
    position: Point
    uncertainty_m: float
    believed_dead: bool


def game_of(tgo: TheaterGroundObject) -> Optional[Game]:
    coalition = getattr(tgo.control_point, "coalition", None)
    return getattr(coalition, "game", None)


def fog_mode(game: Optional[Game]) -> FogOfWar:
    if game is None:
        return FogOfWar.OFF
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return FogOfWar.OFF
    mode = getattr(game.settings, "fog_of_war", FogOfWar.STRICT)
    return mode if isinstance(mode, FogOfWar) else FogOfWar.STRICT


def tgo_view(game: Optional[Game], tgo: TheaterGroundObject) -> Optional[TgoView]:
    """How blue sees a ground object, or None if it should not be shown."""
    mode = fog_mode(game)
    if mode is FogOfWar.OFF or not tgo.control_point.captured.is_red:
        return TgoView(True, True, tgo.position, 0.0, tgo.is_dead)
    assert game is not None
    picture = game.war_state.picture(game, Player.BLUE)
    known = picture.knows(tgo)
    confirmed = known and (picture.confirmed(tgo) or tgo.is_control_point)
    if not known and mode is FogOfWar.STRICT:
        return None
    if known and not confirmed:
        position = picture.estimated_position(tgo)
        uncertainty = picture.error_m(tgo)
    else:
        position = tgo.position
        uncertainty = 0.0
    believed_dead = known and not picture.believed_alive(tgo)
    return TgoView(known, confirmed, position, uncertainty, believed_dead)


def detection_summary(game: Optional[Game], tgo: TheaterGroundObject) -> Optional[str]:
    """One line on how blue knows about an enemy site, e.g. "Detected via
    satellite imagery, turn 2, confidence 72%". None for friendly sites or
    when intel is off."""
    if fog_mode(game) is FogOfWar.OFF or not tgo.control_point.captured.is_red:
        return None
    assert game is not None
    from game.warfare.intel import IntelSource, always_visible

    if always_visible(tgo):
        return "Visible: ships at sea and airbase facilities can't be hidden"
    contact = game.war_state.picture(game, Player.BLUE).contact(tgo)
    if contact is None or not contact.known:
        return "Not detected"
    # A latched decoy looks like a good fix to blue, so it reads like one.
    if contact.source is IntelSource.PREWAR:
        how = "Known from pre-war intelligence"
    else:
        how = f"Detected via {contact.source.value}, turn {contact.last_seen_turn}"
    return f"{how}, confidence {round(contact.confidence * 100)}%"


def tgo_id_visible(game: Game, tgo: TheaterGroundObject) -> bool:
    return tgo_view(game, tgo) is not None


def flight_visible(game: Optional[Game], flight: Flight) -> bool:
    """Whether blue can see an enemy flight right now."""
    if game is None or flight.blue.is_blue or fog_mode(game) is FogOfWar.OFF:
        return True
    if not flight.state.in_flight:
        return False
    try:
        position = flight.state.estimate_position()
    except Exception:
        return False
    return covered_by_blue_radar(game, position)


def covered_by_blue_radar(game: Game, position: Point) -> bool:
    from game.ato.flighttype import FlightType
    from game.theater.theatergroundobject import EwrGroundObject

    for cp in game.theater.control_points_for(Player.BLUE):
        for tgo in cp.ground_objects:
            if isinstance(tgo, EwrGroundObject) and not tgo.is_dead:
                reach = tgo.max_detection_range().meters
                if reach and tgo.position.distance_to_point(position) <= reach:
                    return True
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.flight_type is not FlightType.AEWC or not flight.state.in_flight:
                continue
            if flight.state.estimate_position().distance_to_point(position) <= 350_000:
                return True
    return False


def show_flight_routes(game: Optional[Game], flight: Flight) -> bool:
    return flight.blue.is_blue or fog_mode(game) is FogOfWar.OFF
