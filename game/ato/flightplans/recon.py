from __future__ import annotations

from typing import Type

from .formationattack import (
    FormationAttackBuilder,
    FormationAttackFlightPlan,
    FormationAttackLayout,
)
from ..flightwaypointtype import FlightWaypointType


class ReconFlightPlan(FormationAttackFlightPlan):
    """Unarmed reconnaissance: fly the target area like a strike, take pictures,
    go home. Results feed the intelligence picture (game.warfare.intel)."""

    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder


class Builder(FormationAttackBuilder[ReconFlightPlan, FormationAttackLayout]):
    def layout(self) -> FormationAttackLayout:
        return self._build(FlightWaypointType.INGRESS_RECON)

    def build(self, dump_debug_info: bool = False) -> ReconFlightPlan:
        return ReconFlightPlan(self.flight, self.layout())
