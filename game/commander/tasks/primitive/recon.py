from __future__ import annotations

from dataclasses import dataclass

from game.ato.flighttype import FlightType
from game.commander.tasks.packageplanningtask import PackagePlanningTask
from game.commander.theaterstate import TheaterState
from game.theater.theatergroundobject import TheaterGroundObject


@dataclass
class PlanRecon(PackagePlanningTask[TheaterGroundObject]):
    """Photograph a target: confirm it before striking it, or assess the damage
    after a strike."""

    def preconditions_met(self, state: TheaterState) -> bool:
        if self.target not in state.recon_targets:
            return False
        if not self.target_area_preconditions_met(state):
            return False
        return super().preconditions_met(state)

    def apply_effects(self, state: TheaterState) -> None:
        state.recon_targets.remove(self.target)
        super().apply_effects(state)

    def propose_flights(self) -> None:
        self.propose_flight(FlightType.RECON, 1)
        self.propose_common_escorts()
