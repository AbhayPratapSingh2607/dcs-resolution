from __future__ import annotations

import itertools
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

from typing_extensions import TYPE_CHECKING

from game.ato.flightstate import Uninitialized, Completed, InCombat
from game.settings.settings import FastForwardStopCondition, CombatResolutionMethod
from .combat import CombatInitiator, FrozenCombat
from .combat.model import CombatModel
from .combat.model.airdefense import sead_hunt
from .combat.model.groundbattle import GroundWar
from .gameupdateevents import GameUpdateEvents as _Events
from .simulationresults import SimulationResults

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight
    from .gameupdateevents import GameUpdateEvents


class AircraftSimulation:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.combats: list[FrozenCombat] = []
        self.results = SimulationResults()
        self.model = CombatModel(game, self.results)
        self.ground_war: GroundWar | None = None
        #: False for passes that resolve only air operations (the parts of a
        #: 6 hour ATO period outside the DCS window, game.sim.atoperiod).
        self.ground_war_enabled = True
        #: When set, the ground war only fights inside this time window.
        self.ground_window: tuple[datetime, datetime] | None = None

    def begin_simulation(self, start: datetime | None = None) -> None:
        from .atoperiod import ground_window

        self.reset()
        self.results = SimulationResults()
        self.model = CombatModel(self.game, self.results)
        self.ground_war = None
        self.ground_window = ground_window(self.game)
        if self.ground_war_enabled and getattr(
            self.game.settings, "combat_model_ground_war", True
        ):
            self.ground_war = GroundWar(
                self.model,
                timedelta(
                    minutes=getattr(
                        self.game.settings, "combat_model_ground_interval", 10
                    )
                ),
            )
        self.set_initial_flight_states(start)
        self.results.flights_flown = list(self.iter_flights())

    def on_game_tick(
        self,
        events: GameUpdateEvents,
        time: datetime,
        duration: timedelta,
        combat_resolution_method: CombatResolutionMethod,
        force_continue: bool,
    ) -> None:
        if (
            not self._auto_resolve_combat(combat_resolution_method, force_continue)
            and self.combats
        ):
            logging.error(
                "Cannot resume simulation because aircraft are in combat and "
                "auto-resolve is disabled"
            )
            events.complete_simulation()
            return

        still_active = []
        for combat in self.combats:
            if combat.on_game_tick(
                time,
                duration,
                self.results,
                events,
                combat_resolution_method,
            ):
                events.end_combat(combat)
            else:
                still_active.append(combat)
        self.combats = still_active

        for flight in self.iter_flights():
            flight.on_game_tick(events, time, duration)

        # Finish updating all flights before checking for combat so that the new
        # positions are used.
        CombatInitiator(
            self.game, self.combats, events, self.model
        ).update_active_combats()

        if combat_resolution_method is CombatResolutionMethod.RESOLVE:
            sead_hunt(self.model, time, events)
            if self.ground_war is not None and (
                self.ground_window is None
                or self.ground_window[0] <= time <= self.ground_window[1]
            ):
                self.ground_war.on_game_tick(time)

        # After updating all combat states, check for halts.
        for flight in self.iter_flights():
            if flight.should_halt_sim() and not force_continue:
                events.complete_simulation()
                return

        # Find completed flights, removing them from the ATO and returning aircraft
        # and pilots back to the squadron.
        for flight in self.iter_flights():
            if type(flight.state) == Completed:
                flight.package.remove_flight(flight)
                if len(flight.package.flights) == 0:
                    flight.squadron.coalition.ato.remove_package(flight.package)

        if (
            not self._auto_resolve_combat(combat_resolution_method, force_continue)
            and self.combats
        ):
            events.complete_simulation()

    def has_activity(self) -> bool:
        """True while any flight is still flying (or yet to fly) or fighting."""
        if self.combats:
            return True
        for flight in self.iter_flights():
            if flight.alive and not isinstance(flight.state, Completed):
                return True
        return False

    def set_initial_flight_states(self, start: datetime | None = None) -> None:
        now = start or self.game.conditions.start_time
        for flight in self.iter_flights():
            flight.state.reinitialize(now)

    def reset(self) -> None:
        self.revert_simulated_damage(_Events())
        self.combats = []
        for flight in self.iter_flights():
            flight.set_state(Uninitialized(flight, self.game.settings))

    def revert_simulated_damage(self, events: GameUpdateEvents) -> None:
        """Undoes damage the combat model applied to the in-memory game, e.g. when
        the player cancels the mission."""
        self.results.revert(events)

    def iter_flights(self) -> Iterator[Flight]:
        packages = itertools.chain(
            self.game.blue.ato.packages, self.game.red.ato.packages
        )
        for package in packages:
            yield from package.flights

    def _auto_resolve_combat(
        self, combat_resolution_method: CombatResolutionMethod, force_continue: bool
    ) -> bool:
        if force_continue:
            return True
        return combat_resolution_method != CombatResolutionMethod.PAUSE
