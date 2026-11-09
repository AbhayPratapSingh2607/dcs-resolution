from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from game.ato.starttype import StartType
from .atdeparture import AtDeparture

if TYPE_CHECKING:
    from game.ato.flight import Flight
    from game.settings import Settings
    from game.sim.gameupdateevents import GameUpdateEvents


class OnAlert(AtDeparture):
    """Fighters on ground alert (QRA), armed at the runway end. They don't
    start on a schedule: the side's GCI controller (game.sim.gci) scrambles
    them when its own radars see an enemy raid in their sector."""

    def __init__(self, flight: Flight, settings: Settings) -> None:
        super().__init__(flight, settings)

    def on_game_tick(
        self, events: GameUpdateEvents, time: datetime, duration: timedelta
    ) -> None:
        return

    @property
    def is_waiting_for_start(self) -> bool:
        return True

    def time_remaining(self, time: datetime) -> timedelta:
        return timedelta(0)

    @property
    def spawn_type(self) -> StartType:
        return StartType.RUNWAY

    @property
    def description(self) -> str:
        return "On ground alert"
