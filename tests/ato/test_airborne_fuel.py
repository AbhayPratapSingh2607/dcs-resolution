"""AI flights airborne at mission start spawn with the fuel they have left,
but never less than they need to finish the plan with a reserve (F4)."""

from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.ato.flightstate.airbornefuel import RESERVE_SHARE, airborne_fuel
from game.ato.flightstate.navigating import Navigating
from game.utils import LBS_TO_KG

FULL = 5000.0


def _flight(estimate: float, legs_lbs: list[float], in_flight: bool = True) -> Any:
    waypoints = [object() for _ in range(len(legs_lbs) + 2)]
    consumption = dict(zip(zip(waypoints[1:], waypoints[2:]), legs_lbs))
    plan = SimpleNamespace(
        waypoints=waypoints,
        fuel_consumption_between_points=lambda a, b: consumption[(a, b)],
    )
    flight = SimpleNamespace(
        fuel=FULL,
        unit_type=SimpleNamespace(fuel_consumption=object()),
        flight_plan=plan,
    )
    if in_flight:
        state = Navigating.__new__(Navigating)
        state.waypoint_index = 1
        state.estimate_fuel = lambda: estimate  # type: ignore[method-assign]
    else:
        state = SimpleNamespace()
    flight.state = state
    return flight


def test_spawns_with_the_fuel_it_has_left() -> None:
    assert airborne_fuel(cast(Any, _flight(3500, [100, 100]))) == 3500


def test_never_below_what_it_needs_to_get_home() -> None:
    needed = 2000 * LBS_TO_KG
    fuel = airborne_fuel(cast(Any, _flight(200, [1000, 1000])))
    assert fuel == pytest.approx(needed * 1.3 + FULL * RESERVE_SHARE)


def test_never_more_than_a_full_load() -> None:
    assert airborne_fuel(cast(Any, _flight(9000, [10000, 10000]))) == FULL


def test_flights_on_the_ground_keep_their_load() -> None:
    assert airborne_fuel(cast(Any, _flight(3500, [100], in_flight=False))) is None


def test_returning_flight_without_consumption_data_is_low_on_fuel() -> None:
    from game.ato.flightstate.airbornefuel import RETURNING_SHARE

    flight = _flight(3500, [100])
    flight.unit_type.fuel_consumption = None
    assert airborne_fuel(cast(Any, flight)) is None
    flight.returning = True
    assert airborne_fuel(cast(Any, flight)) == FULL * RETURNING_SHARE
