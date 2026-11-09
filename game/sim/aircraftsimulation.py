from __future__ import annotations

import itertools
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Optional

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
        self._last_observed: Optional[datetime] = None
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
        from game.sim.gci import GciController

        self.gci = GciController(self.game, self.model)
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

        self._ground_unavailable_sorties(time)
        for flight in self.iter_flights():
            flight.on_game_tick(events, time, duration)

        # Ground alert fighters scramble against raids the side's radars see.
        gci = getattr(self, "gci", None)
        if gci is not None:
            try:
                gci.tick(time, self.iter_flights())
            except Exception:
                logging.exception("GCI scramble failed")

        # Finish updating all flights before checking for combat so that the new
        # positions are used.
        CombatInitiator(
            self.game, self.combats, events, self.model
        ).update_active_combats()

        if combat_resolution_method is CombatResolutionMethod.RESOLVE:
            self._observe(time)
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

    def _ground_unavailable_sorties(self, time: datetime) -> None:
        """A second sortie (game.commander.jfacc.sorties) flies airframes that
        flew earlier in the period. If the squadron lost aircraft since, there
        may be none left to fly it: the sortie is cancelled rather than flown
        by airframes that were shot down."""
        from game.ato.flightstate import WaitingForStart

        due = [
            f
            for f in self.iter_flights()
            if f.reused_airframes > 0
            and isinstance(f.state, WaitingForStart)
            and f.state.start_time <= time
        ]
        if not due:
            return
        lost: dict[int, int] = {}
        for loss in self.results.air_losses:
            key = id(loss.flight.squadron)
            lost[key] = lost.get(key, 0) + 1
        for flight in due:
            squadron = flight.squadron
            in_use = 0
            for other in self.iter_flights():
                if other is flight or other.squadron is not squadron:
                    continue
                state = other.state
                if isinstance(state, (WaitingForStart, Completed)) or not other.alive:
                    continue
                in_use += len(self.model.airframes(other)) or other.count
            pool = squadron.owned_aircraft - lost.get(id(squadron), 0)
            if in_use + flight.count <= pool:
                continue
            logging.info(
                f"{flight} cancelled: {squadron} has {pool - in_use} airframes left"
            )
            flight.grounded = True  # type: ignore[attr-defined]
            package = flight.package
            package.remove_flight(flight)
            if not package.flights:
                squadron.coalition.ato.remove_package(package)

    #: How often each side's surveillance picture is sampled for the air
    #: campaign planner's learned threat axes.
    OBSERVE_INTERVAL = timedelta(minutes=5)

    def _observe(self, time: datetime) -> None:
        last = self._last_observed
        if last is not None and time - last < self.OBSERVE_INTERVAL:
            return
        self._last_observed = time
        try:
            from game.commander.jfacc.observations import collect

            self.results.observations.extend(
                collect(self.model, time, self.iter_flights())
            )
        except Exception:
            logging.exception("Could not sample surveillance observations")

    def has_activity(self) -> bool:
        """True while any flight is still flying (or yet to fly) or fighting."""
        if self.combats:
            return True
        from game.sim.gci import is_on_alert

        for flight in self.iter_flights():
            if (
                flight.alive
                and not isinstance(flight.state, Completed)
                and not is_on_alert(flight)
            ):
                return True
        return False

    def set_initial_flight_states(self, start: datetime | None = None) -> None:
        now = start or self.game.conditions.start_time
        for flight in self.iter_flights():
            flight.state.reinitialize(now)

    def reset(self) -> None:
        self.revert_simulated_damage(_Events())
        self.combats = []
        self._last_observed = None
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
