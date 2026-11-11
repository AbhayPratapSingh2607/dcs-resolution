"""V4: FARP deliveries and air assaults flown by the combat model, outside the
DCS mission, take effect when the flight survives."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from game.ato.flighttype import FlightType
from game.sim import offmission
from game.theater.controlpoint import Airfield
from game.theater.dynamicfarp import DynamicFarp
from game.theater.player import Player


class _Flight:
    """Hashable, like a real Flight."""

    def __init__(
        self,
        flight_type: FlightType,
        target: Any,
        player: Player = Player.BLUE,
        clients: int = 0,
    ) -> None:
        self.flight_type = flight_type
        self.client_count = clients
        self.count = 2
        self.squadron = SimpleNamespace(player=player)
        self.package = SimpleNamespace(target=target, flights=[self])


def _game(*flights: _Flight) -> Any:
    packages = [f.package for f in flights]
    coalition = SimpleNamespace(ato=SimpleNamespace(packages=packages))
    return SimpleNamespace(coalitions=[coalition])


def _debriefing(
    flown: tuple[_Flight, ...] = (), lost: Optional[dict[int, int]] = None
) -> Any:
    losses = lost or {}
    return SimpleNamespace(
        unit_map=SimpleNamespace(
            aircraft={i: SimpleNamespace(flight=f) for i, f in enumerate(flown)}
        ),
        air_losses=SimpleNamespace(
            surviving_flight_members=lambda f: f.count - losses.get(id(f), 0)
        ),
        base_captures=[],
    )


def test_only_surviving_ai_flights_outside_the_mission_count() -> None:
    target = object()
    ai = _Flight(FlightType.TRANSPORT, target)
    in_mission = _Flight(FlightType.TRANSPORT, target)
    player = _Flight(FlightType.TRANSPORT, target, clients=1)
    shot_down = _Flight(FlightType.TRANSPORT, target)
    other_task = _Flight(FlightType.CAS, target)
    game = _game(ai, in_mission, player, shot_down, other_task)
    debriefing = _debriefing(flown=(in_mission,), lost={id(shot_down): 2})
    found = list(
        offmission.ai_flights_outside_mission(game, debriefing, FlightType.TRANSPORT)
    )
    assert found == [ai]


def test_a_farp_setup_flight_outside_the_mission_delivers() -> None:
    farp = object.__new__(DynamicFarp)
    farp.__dict__.update(id="farp-1", name="FARP Alpha", established=False)
    flight = _Flight(FlightType.TRANSPORT, farp)
    game = _game(flight)
    assert offmission.farp_deliveries(game, _debriefing()) == ["farp-1"]
    # In the mission, CTLD reports it (or not).
    assert offmission.farp_deliveries(game, _debriefing(flown=(flight,))) == []
    farp.established = True
    assert offmission.farp_deliveries(game, _debriefing()) == []


def _base(armor: int, owner: Player = Player.RED) -> Airfield:
    cp = object.__new__(Airfield)
    cp.__dict__.update(
        id=f"cp-{armor}",
        name=f"Base {armor}",
        _coalition=SimpleNamespace(player=owner),
        base=SimpleNamespace(total_armor=armor),
    )
    return cp


def test_an_air_assault_outside_the_mission_takes_an_undefended_base() -> None:
    empty, held, own = _base(0), _base(3), _base(0, Player.BLUE)
    game = _game(
        _Flight(FlightType.AIR_ASSAULT, empty),
        _Flight(FlightType.AIR_ASSAULT, held),
        _Flight(FlightType.AIR_ASSAULT, own),
    )
    captures = offmission.air_assault_captures(game, _debriefing())
    assert [(c.control_point, c.captured_by_player) for c in captures] == [
        (empty, Player.BLUE)
    ]
