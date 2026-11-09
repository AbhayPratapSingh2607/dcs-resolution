from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, TYPE_CHECKING

from .gamelooptimer import GameLoopTimer
from .gameupdatecallbacks import GameUpdateCallbacks
from .gameupdateevents import GameUpdateEvents
from .missionsimulation import MissionSimulation, SimulationAlreadyCompletedError
from .simspeedsetting import SimSpeedSetting

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing


class GameLoop:
    def __init__(self, game: Game, callbacks: GameUpdateCallbacks) -> None:
        self.game = game
        self.callbacks = callbacks
        self.timer = GameLoopTimer(self.tick)
        self.sim = MissionSimulation(self.game)
        self.events = GameUpdateEvents()
        self.last_update_time = datetime.now()
        self.started = False
        self.completed = False

    @property
    def current_time_in_sim(self) -> datetime:
        return self.sim.time

    @property
    def elapsed_time(self) -> timedelta:
        return self.sim.time - self.game.conditions.start_time

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Cannot start game loop because it has already started")
        self.started = True
        self.sim.begin_simulation()

    def pause(self) -> None:
        self.set_simulation_speed(SimSpeedSetting.PAUSED)

    def set_simulation_speed(self, simulation_speed: SimSpeedSetting) -> None:
        self.timer.stop()
        if simulation_speed != self.timer.simulation_speed:
            logging.info(f"Speed changed to {simulation_speed}")
        if not self.started and simulation_speed is not SimSpeedSetting.PAUSED:
            self.start()
        self.timer.set_speed(simulation_speed)

    @contextmanager
    def paused_sim(self) -> Iterator[None]:
        with self.timer.locked_pause():
            yield

    def revert_simulated_damage(self) -> None:
        events = GameUpdateEvents()
        self.sim.aircraft_simulation.revert_simulated_damage(events)
        if not events.empty:
            self.callbacks.on_update(events)

    def run_to_first_contact(self) -> None:
        self.pause()
        if not self.started:
            self.start()
        logging.info("Running sim to first contact")
        while not self.completed:
            self.tick(suppress_events=False)

    def advance_to_window(self) -> None:
        """Resolve the ATO period up to the chosen DCS window and hold back
        packages that start after it (game.sim.atoperiod)."""
        from .atoperiod import align_player_packages, defer_after_window

        self.pause()
        if not self.started:
            self.start()
        align_player_packages(self.game, self.sim.time)
        self.sim.advance_to_window(self.events)
        defer_after_window(self.game)
        self.send_update(rate_limit=False)

    def pause_and_generate_miz(self, output: Path) -> None:
        self.pause()
        if not self.started:
            self.start()
        self.sim.generate_miz(output)

    def pause_and_debrief(self, state_path: Path, force_end: bool) -> Debriefing:
        self.pause()
        return self.sim.debrief_current_state(state_path, force_end)

    def complete_with_results(self, debriefing: Debriefing) -> None:
        from .atoperiod import resolve_remainder

        self.pause()
        self.sim.process_results(debriefing, self.events)
        # Packages held back past the DCS window are fought now.
        remainder = resolve_remainder(self.game, self.events)
        if remainder is not None:
            debriefing.remainder = remainder  # type: ignore[attr-defined]
        self.completed = True
        self.send_update(rate_limit=False)

    def send_update(self, rate_limit: bool) -> None:
        # We don't skip empty events because we still want the tick in the Qt part of
        # the UI, which will update things like the current simulation time. The time
        # probably be an "event" of its own. For now the websocket endpoint will filter
        # out empty events to avoid the map handling unnecessary events, but we still
        # pass the events through to Qt.
        now = datetime.now()
        time_since_update = now - self.last_update_time
        if not rate_limit or time_since_update >= timedelta(seconds=1 / 60):
            self.callbacks.on_update(self.events)
            self.events = GameUpdateEvents()
            self.last_update_time = now

    def tick(self, suppress_events: bool = False) -> None:
        if not self.started:
            raise RuntimeError("Attempted to tick game loop before initialization")
        try:
            self.sim.tick(
                self.events,
                self.game.settings.combat_resolution_method,
                force_continue=False,
            )
            self.completed = self.events.simulation_complete
            if not suppress_events:
                self.send_update(rate_limit=True)
            if self.completed:
                self.pause()
                self.send_update(rate_limit=False)
                logging.info(f"Simulation completed at {self.sim.time}")
                self.callbacks.on_simulation_complete()
        except SimulationAlreadyCompletedError:
            logging.exception("Attempted to tick already completed sim")
