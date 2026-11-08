"""Fuel and air-to-air refueling.

Each flight gets a fuel margin (0..1): how much fuel it has left to fight,
loiter and re-attack once it reaches its target. A short hop leaves plenty; a
mission flown near the edge of the aircraft's combat radius leaves almost
nothing. A friendly tanker in reach (one planned into the package, or a
theater tanker on its orbit nearby) tops the flight up, but only for aircraft
that can refuel in the air.

The margin is checked again whenever it is needed, so a tanker that is shot
down stops supporting its flights at once.

Effects:

* **Air-to-air:** fighters short of fuel reach bingo sooner, and fighters
  with a tanker behind them later. Most model air fights are decided within
  two minutes, so this only matters in the occasional long fight; how long a
  CAP stays on station is set by its flight plan, not here.
* **Strikes:** a flight at the edge of its range has no time to set up and
  makes one rushed pass, and may turn back short of the target.

See resources/combat/fuel.yaml for combat radii and which aircraft can refuel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional, TYPE_CHECKING

from .engine import clamp, distance_km
from .profiles import _load_yaml, parse_year

if TYPE_CHECKING:
    from game.ato import Flight
    from game.dcs.aircrafttype import AircraftType
    from .engine import CombatModel

#: Margin with a tanker in reach.
TANKER_MARGIN = 0.85
#: Theater tankers this far from a flight can still support it, km.
TANKER_REACH_KM = 450.0
#: Seconds of air combat before fighters start reaching bingo, with plenty of
#: fuel and with none.
BINGO_FULL_S = 300.0
BINGO_EMPTY_S = 180.0
#: Extra time in a fight with a tanker to go back to.
TANKER_EXTRA_S = 120.0
#: Below this margin, strike flights make a single rushed pass.
RUSHED_MARGIN = 0.35
#: Below this margin, strike flights may turn back before the target.
ABORT_MARGIN = 0.1


@dataclass(frozen=True)
class FuelProfile:
    radius_km: float
    can_refuel: bool


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    try:
        return _load_yaml("fuel.yaml") or {}
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=None)
def fuel_profile(aircraft: AircraftType) -> FuelProfile:
    from game.ato.flighttype import FlightType

    data = _data()
    dcs = aircraft.dcs_unit_type
    dcs_id = getattr(dcs, "id", "")
    fuel = float(getattr(dcs, "fuel_max", 0) or 0)
    heavy = (
        aircraft.capable_of(FlightType.AEWC)
        or aircraft.capable_of(FlightType.REFUELING)
        or aircraft.capable_of(FlightType.TRANSPORT)
        or fuel > 25000
    )
    if aircraft.helicopter:
        radius = 150.0
    elif heavy:
        radius = 2000.0
    else:
        radius = 250.0 + 0.08 * fuel
    radius = float(data.get("radius_km", {}).get(dcs_id, radius))
    year = parse_year(aircraft.year_introduced)
    can_refuel = (
        not aircraft.helicopter
        and year >= 1960
        and dcs_id not in set(data.get("no_aar", []))
    )
    return FuelProfile(radius, can_refuel)


def mission_distance_km(flight: Flight) -> Optional[float]:
    """Distance from the flight's base to its target, if both are known."""
    departure = getattr(flight, "departure", None)
    target = getattr(getattr(flight, "package", None), "target", None)
    start = getattr(departure, "position", None)
    end = getattr(target, "position", None)
    if start is None or end is None:
        return None
    try:
        return distance_km(start, end)
    except Exception:
        return None


def _airborne_tankers(model: CombatModel, flight: Flight, now: datetime) -> list[Any]:
    from game.ato.flighttype import FlightType

    player = flight.squadron.player
    key = (player.is_blue, now)
    cache: dict[tuple[bool, datetime], list[Any]] = model.__dict__.setdefault(
        "_tanker_cache", {}
    )
    if key not in cache:
        if len(cache) > 8:
            cache.clear()
        tankers = []
        for package in model.game.coalition_for(player).ato.packages:
            for other in package.flights:
                if other.flight_type is not FlightType.REFUELING:
                    continue
                if not other.alive or not other.state.in_flight:
                    continue
                if not model.airframes(other):
                    continue
                tankers.append(other)
        cache[key] = tankers
    return cache[key]


def tanker_support(model: CombatModel, flight: Flight, now: datetime) -> bool:
    """Whether a live friendly tanker can top this flight up."""
    if not fuel_profile(flight.unit_type).can_refuel:
        return False
    tankers = _airborne_tankers(model, flight, now)
    if not tankers:
        return False
    if any(t.package is flight.package for t in tankers):
        return True
    try:
        position = flight.state.estimate_position()
    except Exception:
        return False
    return any(
        distance_km(t.state.estimate_position(), position) <= TANKER_REACH_KM
        for t in tankers
    )


def fuel_margin(model: CombatModel, flight: Flight, now: datetime) -> float:
    """Fuel left to fight with at the target, 0..1."""
    margin = 1.0
    distance = mission_distance_km(flight)
    if distance is not None:
        ratio = distance / max(fuel_profile(flight.unit_type).radius_km, 1.0)
        # Within half the radius there's fuel to spare; at the radius only a
        # quarter is left; beyond it, quickly nothing.
        margin = clamp(1.75 - ratio * 1.5, 0.0, 1.0)
    if margin < TANKER_MARGIN and tanker_support(model, flight, now):
        margin = TANKER_MARGIN
    return margin


def bingo_after_s(model: CombatModel, flight: Flight, now: datetime) -> float:
    """Seconds into an air fight before the flight starts reaching bingo."""
    margin = fuel_margin(model, flight, now)
    seconds = BINGO_EMPTY_S + (BINGO_FULL_S - BINGO_EMPTY_S) * margin
    if tanker_support(model, flight, now):
        seconds += TANKER_EXTRA_S
    return seconds


def strike_accuracy_factor(margin: float) -> float:
    """A rushed single pass at the edge of range."""
    if margin >= RUSHED_MARGIN:
        return 1.0
    return 0.8 + 0.2 * margin / RUSHED_MARGIN


def strike_abort_chance(margin: float) -> float:
    """Chance a strike flight turns back before reaching its target."""
    if margin >= ABORT_MARGIN:
        return 0.0
    return min(0.5, (ABORT_MARGIN - margin) * 5)
