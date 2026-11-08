from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from game.ato.flightstate import InCombat, InFlight
from game.settings.settings import CombatResolutionMethod
from .. import GameUpdateEvents

if TYPE_CHECKING:
    from game.ato import Flight
    from ..simulationresults import SimulationResults
    from .model import CombatModel


class FrozenCombat(ABC):
    """A combat that holds its flights in place while it is resolved.

    With the combat model enabled, combat is resolved over simulated time: the
    combat advances its model every tick and ends when the model says the fight
    is over, so a short skirmish frees its flights sooner than a long furball.
    Without a model (or when skipping combat) the old fixed freeze applies.
    """

    def __init__(self, freeze_duration: timedelta) -> None:
        self.id = uuid.uuid4()
        self.freeze_duration = freeze_duration
        self.elapsed_time = timedelta()
        self.model: Optional[CombatModel] = None
        self._model_started = False

    def on_game_tick(
        self,
        time: datetime,
        duration: timedelta,
        results: SimulationResults,
        events: GameUpdateEvents,
        resolution_method: CombatResolutionMethod,
    ) -> bool:
        self.elapsed_time += duration
        if (
            resolution_method is not CombatResolutionMethod.SKIP
            and self.model is not None
        ):
            if not self._model_started:
                self._model_started = True
                self.begin_model(time - duration, events)
            if self.advance_model(time, duration, events):
                self.finish_model(time, self.elapsed_time, events)
                return True
            return False
        if self.elapsed_time >= self.freeze_duration:
            self.resolve(results, events, time, self.elapsed_time, resolution_method)
            return True
        return False

    def begin_model(self, time: datetime, events: GameUpdateEvents) -> None:
        """Sets up the model-driven engagement."""

    def advance_model(
        self, time: datetime, duration: timedelta, events: GameUpdateEvents
    ) -> bool:
        """Advances the model-driven engagement. Returns True when it is over."""
        return self.elapsed_time >= self.freeze_duration

    def finish_model(
        self, time: datetime, elapsed_time: timedelta, events: GameUpdateEvents
    ) -> None:
        """Applies the outcome of the model-driven engagement and releases flights."""
        self.release_flights(events, time, elapsed_time)

    def release_flights(
        self,
        events: GameUpdateEvents,
        time: datetime,
        elapsed_time: timedelta,
        avoid_further_combat: bool = False,
        aborted: Optional[list[Flight]] = None,
    ) -> None:
        aborted = aborted or []
        for flight in list(self.iter_flights()):
            if not flight.alive:
                continue
            state = flight.state
            if not isinstance(state, InCombat):
                continue
            state.exit_combat(events, time, elapsed_time, avoid_further_combat)
            if flight in aborted and flight.state.in_flight:
                try:
                    flight.abort()
                except Exception:
                    import logging

                    logging.exception(f"Could not abort {flight}")
            events.update_flight(flight)

    @abstractmethod
    def resolve(
        self,
        results: SimulationResults,
        events: GameUpdateEvents,
        time: datetime,
        elapsed_time: timedelta,
        resolution_method: CombatResolutionMethod,
    ) -> None: ...

    @abstractmethod
    def because(self) -> str: ...

    @abstractmethod
    def describe(self) -> str: ...

    @abstractmethod
    def iter_flights(self) -> Iterator[Flight]: ...

    def update_flight_states(self) -> None:
        for flight in self.iter_flights():
            if not isinstance(flight.state, InFlight):
                raise RuntimeError(
                    f"Found non in-flight aircraft engaged in combat: {flight}"
                )
            flight.set_state(InCombat(flight.state, self))
