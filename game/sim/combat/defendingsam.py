from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from game.ato.flightstate import InCombat
from game.settings.settings import CombatResolutionMethod
from .frozencombat import FrozenCombat
from .. import GameUpdateEvents

if TYPE_CHECKING:
    from game.ato import Flight
    from game.theater import TheaterGroundObject
    from ..simulationresults import SimulationResults
    from .model.airdefense import AirDefenseEngagement


class DefendingSam(FrozenCombat):
    """A flight inside the engagement zone of enemy air defenses.

    With the combat model this is one engagement window: the sites shoot for
    ``freeze_duration`` of simulated time (or until they can no longer reach
    the flight). A flight that is still inside a threat zone afterwards will be
    engaged again, so time spent in the zone is what costs aircraft.
    """

    def __init__(
        self,
        freeze_duration: timedelta,
        flight: Flight,
        air_defenses: list[TheaterGroundObject],
    ) -> None:
        super().__init__(freeze_duration)
        self.flight = flight
        self.air_defenses = air_defenses
        self.engagement: Optional[AirDefenseEngagement] = None

    def because(self) -> str:
        sams = ", ".join(str(d) for d in self.air_defenses)
        return f"{self.flight} is engaged by enemy air defenses: {sams}"

    def describe(self) -> str:
        return f"engaged by enemy air defenses"

    def iter_flights(self) -> Iterator[Flight]:
        yield self.flight

    def begin_model(self, time: datetime, events: GameUpdateEvents) -> None:
        from .model.airdefense import AirDefenseEngagement

        assert self.model is not None
        self.engagement = AirDefenseEngagement.create(
            self.model, self.flight, self.air_defenses, time, self.freeze_duration
        )

    def advance_model(
        self, time: datetime, duration: timedelta, events: GameUpdateEvents
    ) -> bool:
        assert self.engagement is not None
        return self.engagement.step(duration.total_seconds(), events)

    def finish_model(
        self, time: datetime, elapsed_time: timedelta, events: GameUpdateEvents
    ) -> None:
        assert self.engagement is not None
        aborted = [self.flight] if self.engagement.aborted else []
        self.release_flights(events, time, elapsed_time, aborted=aborted)

    def resolve(
        self,
        results: SimulationResults,
        events: GameUpdateEvents,
        time: datetime,
        elapsed_time: timedelta,
        resolution_method: CombatResolutionMethod,
    ) -> None:
        # Only reached without a combat model, or when skipping combat.
        if isinstance(self.flight.state, InCombat):
            logging.debug(f"Air defense combat with {self.flight} skipped")
            self.flight.state.exit_combat(events, time, elapsed_time)
