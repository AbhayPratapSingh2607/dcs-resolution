""" "Fast-forward the turn" (no player flight) fights the whole turn whatever
the fast-forward setting says."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from game.settings.settings import FastForwardStopCondition
from game.sim.gameupdateevents import GameUpdateEvents
from game.sim.missionsimulation import MissionSimulation


def _sim(whole_turn: bool) -> Any:
    sim: Any = object.__new__(MissionSimulation)
    sim.game = SimpleNamespace(
        settings=SimpleNamespace(
            fast_forward_stop_condition=FastForwardStopCondition.PLAYER_STARTUP
        ),
        ato_has_clients=lambda: False,
    )
    sim.aircraft_simulation = MagicMock()
    sim.completed = False
    sim.time = datetime(2026, 1, 1, 5)
    sim.whole_turn = whole_turn
    sim.simulated_turn_over = lambda: False
    return sim


def test_without_players_a_player_stop_condition_ends_at_once() -> None:
    sim = _sim(whole_turn=False)
    events = sim.tick(GameUpdateEvents(), MagicMock(), False)
    assert events.simulation_complete
    sim.aircraft_simulation.on_game_tick.assert_not_called()


def test_fast_forwarding_the_turn_fights_it() -> None:
    sim = _sim(whole_turn=True)
    events = sim.tick(GameUpdateEvents(), MagicMock(), False)
    assert not events.simulation_complete
    sim.aircraft_simulation.on_game_tick.assert_called_once()
