"""Second sorties are cancelled when the squadron's airframes were shot down
(AircraftSimulation._ground_unavailable_sorties)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flightstate import WaitingForStart
from game.sim.aircraftsimulation import AircraftSimulation

NOW = datetime(2020, 6, 1, 10, 0)


class _Package:
    def __init__(self) -> None:
        self.flights: list[Any] = []

    def remove_flight(self, flight: Any) -> None:
        self.flights.remove(flight)


def _flight(squadron: Any, count: int, reused: int, waiting: bool) -> Any:
    package = _Package()
    flight = SimpleNamespace(
        squadron=squadron, count=count, reused_airframes=reused, alive=True, package=package
    )
    if waiting:
        state = WaitingForStart.__new__(WaitingForStart)
        state.start_time = NOW - timedelta(minutes=1)
        flight.state = state
    else:
        flight.state = SimpleNamespace()
    package.flights.append(flight)
    squadron.coalition.ato.packages.append(package)
    return flight


def _sim(flights: list[Any], losses: int, squadron: Any) -> AircraftSimulation:
    sim = AircraftSimulation.__new__(AircraftSimulation)
    sim.results = SimpleNamespace(  # type: ignore[assignment]
        air_losses=[SimpleNamespace(flight=SimpleNamespace(squadron=squadron))] * losses
    )
    sim.model = SimpleNamespace(airframes=lambda f: [object()] * f.count)  # type: ignore[assignment]
    sim.iter_flights = lambda: [f for p in squadron.coalition.ato.packages for f in p.flights]  # type: ignore[method-assign]
    return sim


def _squadron(owned: int) -> Any:
    ato = SimpleNamespace(packages=[])
    ato.remove_package = ato.packages.remove
    return SimpleNamespace(owned_aircraft=owned, coalition=SimpleNamespace(ato=ato))


def test_second_sortie_flies_when_airframes_survive() -> None:
    squadron = _squadron(owned=6)
    airborne = _flight(squadron, 2, 0, waiting=False)
    second = _flight(squadron, 2, 2, waiting=True)
    _sim([airborne, second], losses=2, squadron=squadron)._ground_unavailable_sorties(NOW)
    assert not getattr(second, "grounded", False)


def test_second_sortie_is_cancelled_when_its_airframes_were_lost() -> None:
    squadron = _squadron(owned=4)
    airborne = _flight(squadron, 2, 0, waiting=False)
    second = _flight(squadron, 4, 4, waiting=True)
    sim = _sim([airborne, second], losses=2, squadron=squadron)
    sim._ground_unavailable_sorties(NOW)
    assert second.grounded
    assert all(second not in p.flights for p in squadron.coalition.ato.packages)
    assert len(squadron.coalition.ato.packages) == 1
