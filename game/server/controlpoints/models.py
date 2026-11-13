from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from game.server.leaflet import LeafletPoint

if TYPE_CHECKING:
    from game import Game
    from game.theater import ControlPoint


class ControlPointJs(BaseModel):
    id: UUID
    name: str
    blue: bool
    position: LeafletPoint
    mobile: bool
    destination: LeafletPoint | None
    sidc: str
    dynamic_farp_kind: str | None = None
    #: Blue's planned strikes at this airfield (game.warfare.firemissions).
    strikes: list[str] = []

    class Config:
        title = "ControlPoint"

    @staticmethod
    def for_control_point(
        control_point: ControlPoint, strikes: dict[Any, list[str]] | None = None
    ) -> ControlPointJs:
        destination = None
        if control_point.target_position is not None:
            destination = control_point.target_position.latlng()
        if control_point.captured.is_blue:
            blue = True
        else:
            blue = False
        from game.theater.dynamicfarp import DynamicFarp

        farp_kind = (
            control_point.kind if isinstance(control_point, DynamicFarp) else None
        )
        return ControlPointJs(
            id=control_point.id,
            name=control_point.name,
            blue=blue,
            position=control_point.position.latlng(),
            mobile=control_point.moveable and control_point.captured.is_blue,
            destination=destination,
            sidc=str(control_point.sidc()),
            dynamic_farp_kind=farp_kind.value if farp_kind is not None else None,
            strikes=_strikes_at(control_point, strikes),
        )

    @staticmethod
    def all_in_game(game: Game) -> list[ControlPointJs]:
        from game.server.tgos.models import _strike_labels

        strikes = _strike_labels(game)
        return [
            ControlPointJs.for_control_point(cp, strikes)
            for cp in game.theater.controlpoints
        ]


class FarpSiteCheckJs(BaseModel):
    valid: bool
    reasons: list[str]
    #: Risks that don't stop the site being used (a Rescue King near enemy
    #: fighter bases).
    warnings: list[str] = []
    cost: int

    class Config:
        title = "FarpSiteCheck"


class NewFarpJs(BaseModel):
    position: LeafletPoint
    kind: str

    class Config:
        title = "NewFarp"


def _strikes_at(
    control_point: ControlPoint, strikes: dict[Any, list[str]] | None
) -> list[str]:
    from game.server.tgos.models import _strike_labels

    if strikes is None:
        strikes = _strike_labels(control_point.coalition.game)
    return list(strikes.get(control_point.id, []))
