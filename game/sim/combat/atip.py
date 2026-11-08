from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from game.settings.settings import CombatResolutionMethod
from .frozencombat import FrozenCombat
from .. import GameUpdateEvents
from ...ato.flightstate import InCombat

if TYPE_CHECKING:
    from game.ato import Flight
    from ..simulationresults import SimulationResults


class AtIp(FrozenCombat):
    """A flight at its IP flying the attack on its target.

    With the combat model the attack is resolved when the run completes: the
    flight runs the target's point defenses and delivers its weapons. Without
    the model the attack is skipped (mission failure, no losses).
    """

    def __init__(self, freeze_duration: timedelta, flight: Flight) -> None:
        super().__init__(freeze_duration)
        self.flight = flight

    def because(self) -> str:
        return f"{self.flight} is at its IP"

    def describe(self) -> str:
        return f"at IP"

    def iter_flights(self) -> Iterator[Flight]:
        yield self.flight

    def finish_model(
        self, time: datetime, elapsed_time: timedelta, events: GameUpdateEvents
    ) -> None:
        from .model.attack import AttackRun

        assert self.model is not None
        try:
            AttackRun(self.model, self.flight, time, events).run()
        except Exception:
            logging.exception(f"Combat model failed to resolve attack by {self.flight}")
        self.release_flights(events, time, elapsed_time, avoid_further_combat=True)

    def resolve(
        self,
        results: SimulationResults,
        events: GameUpdateEvents,
        time: datetime,
        elapsed_time: timedelta,
        resolution_method: CombatResolutionMethod,
    ) -> None:
        logging.debug(
            f"{self.flight} attack on {self.flight.package.target} skipped with "
            "mission failure but no losses"
        )
        assert isinstance(self.flight.state, InCombat)
        self.flight.state.exit_combat(
            events, time, elapsed_time, avoid_further_combat=True
        )
