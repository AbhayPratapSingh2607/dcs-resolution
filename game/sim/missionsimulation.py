from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from game.debriefing import Debriefing
from game.missiongenerator import MissionGenerator
from game.settings.settings import FastForwardStopCondition, CombatResolutionMethod
from game.unitmap import UnitMap
from .aircraftsimulation import AircraftSimulation
from .missionresultsprocessor import MissionResultsProcessor
from ..profiling import logged_duration

if TYPE_CHECKING:
    from game import Game
    from .gameupdateevents import GameUpdateEvents


TICK = timedelta(seconds=1)


class SimulationAlreadyCompletedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Simulation already completed")


class MissionSimulation:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.unit_map: Optional[UnitMap] = None
        self.aircraft_simulation = AircraftSimulation(self.game)
        self.completed = False
        self.time = self.game.conditions.start_time
        self.miz_generated_at: float = 0.0

    def begin_simulation(self) -> None:
        self.time = self.game.conditions.start_time
        self.aircraft_simulation.begin_simulation()

    def tick(
        self,
        events: GameUpdateEvents,
        combat_resolution_method: CombatResolutionMethod,
        force_continue: bool,
    ) -> GameUpdateEvents:
        self.time += TICK
        if self.completed:
            raise RuntimeError("Simulation already completed")
        stop_condition = self.game.settings.fast_forward_stop_condition
        if stop_condition is FastForwardStopCondition.END_OF_TURN:
            # The whole turn is fought by the combat model; nothing can pause it.
            self.aircraft_simulation.on_game_tick(
                events, self.time, TICK, CombatResolutionMethod.RESOLVE, True
            )
            if self.simulated_turn_over():
                events.complete_simulation()
            self.completed = events.simulation_complete
            return events
        if (
            self.game.settings.fast_forward_stop_condition
            == FastForwardStopCondition.DISABLED
        ):
            events.complete_simulation()
            return events

        # Stop fast forward if there are no clients and the settings require a player to reach a certain state.
        if (
            not self.game.ato_has_clients()
            and self.game.settings.fast_forward_stop_condition
            in {
                FastForwardStopCondition.PLAYER_TAKEOFF,
                FastForwardStopCondition.PLAYER_TAXI,
                FastForwardStopCondition.PLAYER_STARTUP,
                FastForwardStopCondition.PLAYER_AT_IP,
            }
        ):
            events.complete_simulation()
            return events

        self.aircraft_simulation.on_game_tick(
            events, self.time, TICK, combat_resolution_method, force_continue
        )
        self.completed = events.simulation_complete
        return events

    def advance_to_window(self, events: GameUpdateEvents) -> bool:
        """Fight the part of the ATO period before the DCS window with the
        combat model (game.sim.atoperiod). Returns True if time advanced."""
        from .atoperiod import window

        bounds = window(self.game)
        if bounds is None or bounds[0] <= self.time:
            return False
        with logged_duration("Resolving the ATO period before the DCS window"):
            while self.time < bounds[0]:
                self.time += TICK
                self.aircraft_simulation.on_game_tick(
                    events, self.time, TICK, CombatResolutionMethod.RESOLVE, True
                )
        return True

    def simulated_turn_over(self) -> bool:
        from .atoperiod import simulated_turn_limit

        elapsed = self.time - self.game.conditions.start_time
        limit = simulated_turn_limit(self.game)
        if elapsed >= limit:
            return True
        if elapsed < timedelta(minutes=5):
            return False
        return not self.aircraft_simulation.has_activity()

    def debrief_simulated(self) -> Debriefing:
        """Debriefing for a turn fought entirely by the combat model."""
        if self.unit_map is None:
            self.unit_map = UnitMap()
        debriefing = Debriefing({"mission_ended": True}, self.game, self.unit_map)
        debriefing.simulated = True
        debriefing.merge_simulation_results(self.aircraft_simulation.results)
        return debriefing

    def generate_miz(self, output: Path) -> None:
        with logged_duration("Mission generation"):
            self.unit_map = MissionGenerator(self.game, self.time).generate_miz(output)
        self.miz_generated_at = time.time()

    def debrief_current_state(
        self, state_path: Path, force_end: bool = False
    ) -> Debriefing:
        if self.unit_map is None:
            raise RuntimeError(
                "Simulation has no unit map. Results processing began before a mission "
                "was generated."
            )

        with state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)
        if force_end:
            data["mission_ended"] = True
        debriefing = Debriefing(data, self.game, self.unit_map)
        debriefing.merge_simulation_results(self.aircraft_simulation.results)
        return debriefing

    def process_results(self, debriefing: Debriefing, events: GameUpdateEvents) -> None:
        if self.unit_map is None:
            raise RuntimeError(
                "Simulation has no unit map. Results processing began before a mission "
                "was generated."
            )

        MissionResultsProcessor(self.game).commit(debriefing, events)
        # The simulated damage is now part of the game; it must not be reverted.
        self.aircraft_simulation.results.forget_undo()

    def finish(self) -> None:
        self.unit_map = None
