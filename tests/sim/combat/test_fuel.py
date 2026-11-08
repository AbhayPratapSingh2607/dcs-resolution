"""Fuel margin and tanker support in the fast-forward combat model."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs import planes

from game.ato.flighttype import FlightType
from game.dcs.aircrafttype import AircraftType
from game.sim.combat.model.fuel import (
    ABORT_MARGIN,
    BINGO_FULL_S,
    bingo_after_s,
    fuel_margin,
    fuel_profile,
    strike_abort_chance,
    strike_accuracy_factor,
    tanker_support,
)
from game.sim.combat.model.scenario import Scenario, loadout, point
from game.theater.player import Player


def _f16(s: Scenario, base_km: float, target_km: float = 0.0, **kwargs: Any) -> Any:
    flight = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        2,
        loadout(),
        point(target_km, 0),
        **kwargs,
    )
    flight.departure = SimpleNamespace(position=point(target_km - base_km, 0))
    flight.package.target = SimpleNamespace(position=point(target_km, 0), name="Target")
    return flight


def _tanker(s: Scenario, x_km: float, package: Any = None) -> Any:
    return s.flight(
        Player.BLUE,
        planes.KC_135,
        FlightType.REFUELING,
        1,
        loadout(),
        point(x_km, 0),
        package=package,
    )


def test_profiles() -> None:
    Scenario(1)
    f16 = fuel_profile(next(AircraftType.for_dcs_type(planes.F_16C_50)))
    assert 450 <= f16.radius_km <= 600 and f16.can_refuel
    mig21 = fuel_profile(next(AircraftType.for_dcs_type(planes.MiG_21Bis)))
    assert not mig21.can_refuel
    a10 = fuel_profile(next(AircraftType.for_dcs_type(planes.A_10C)))
    assert a10.radius_km == 460


def test_margin_falls_with_distance() -> None:
    s = Scenario(1)
    near = _f16(s, 150)
    far = _f16(s, 500)
    beyond = _f16(s, 800)
    assert fuel_margin(s.model, near, s.time) == 1.0
    assert 0.1 < fuel_margin(s.model, far, s.time) < 0.5
    assert fuel_margin(s.model, beyond, s.time) == 0.0
    # Unknown base or target: assume the planner kept it in range.
    unknown = s.flight(
        Player.BLUE, planes.F_16C_50, FlightType.STRIKE, 2, loadout(), point(0, 0)
    )
    assert fuel_margin(s.model, unknown, s.time) == 1.0


def test_tanker_tops_up_and_extends_the_fight() -> None:
    s = Scenario(1)
    far = _f16(s, 600)
    alone = bingo_after_s(s.model, far, s.time)
    assert alone < BINGO_FULL_S
    _tanker(s, -200)
    s.model.__dict__.pop("_tanker_cache", None)
    assert tanker_support(s.model, far, s.time)
    assert fuel_margin(s.model, far, s.time) >= 0.85
    assert bingo_after_s(s.model, far, s.time) > BINGO_FULL_S


def test_package_tanker_supports_wherever_it_is() -> None:
    s = Scenario(1)
    far = _f16(s, 600)
    _tanker(s, -2000, package=far.package)
    assert tanker_support(s.model, far, s.time)


def test_distant_or_dead_tanker_does_not_help() -> None:
    s = Scenario(1)
    far = _f16(s, 600)
    tanker = _tanker(s, -1500)
    assert not tanker_support(s.model, far, s.time)
    s2 = Scenario(1)
    far2 = _f16(s2, 600)
    tanker = _tanker(s2, -100)
    tanker.state.alive = False
    assert not tanker_support(s2.model, far2, s2.time)


def test_aircraft_without_refueling_get_no_help() -> None:
    s = Scenario(1)
    mig = s.flight(
        Player.BLUE, planes.MiG_21Bis, FlightType.STRIKE, 2, loadout(), point(0, 0)
    )
    mig.departure = SimpleNamespace(position=point(-400, 0))
    mig.package.target = SimpleNamespace(position=point(0, 0), name="Target")
    _tanker(s, -50, package=mig.package)
    assert not tanker_support(s.model, mig, s.time)
    assert fuel_margin(s.model, mig, s.time) < 0.1  # The tanker changes nothing.


def test_strike_penalties_only_at_the_edge_of_range() -> None:
    assert strike_accuracy_factor(1.0) == 1.0
    assert strike_accuracy_factor(0.5) == 1.0
    assert 0.8 <= strike_accuracy_factor(0.0) < 0.85
    assert strike_abort_chance(ABORT_MARGIN) == 0.0
    assert 0.4 <= strike_abort_chance(0.0) <= 0.5
